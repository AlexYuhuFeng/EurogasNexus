"""One hub, one code: stored rows under a hub's other name move to its registry code.

The Danish trading point (joint DK/SE balancing zone) was two hubs: ``ETF``, the name EEX
lists it under, and ``GTF``, Energinet's and the OTC market's name. They are one hub (owner
decision 2026-11-26): the market reference model codes it ``ETF`` with ``GTF`` as an alias,
and every intake now stores the code. Likewise ``VTP``, which the screen import stored as a
hub of its own, is CEGH. This revision moves what was stored under the other names:

- every hub column (``hub``, ``buy_hub``/``sell_hub``, ``hub_id``, ``market_hub``) and the
  reference network's trading-point code (``reference_market_hubs.hub_code``, so the map
  node and the routes name the hub the prices do; skipped where the code is already held);
- hub lists held as JSON (mandate hubs, news tags);
- price observations named ``"GTF <product>"``, with the hub in their metadata;
- simulated (demo) quotes, trades and closes under ``GTF`` are deleted, not moved: the demo
  priced ETF and GTF as two invented series, and moving one onto the other would give one
  hub two prices for a day. The demo writes ETF's again on its next roll-forward.

It also stores the demo board's quote keys the way the tick intake and the screen import do
(``products.board_tenor``): ``jan-27``, not ``Jan-27``, and ``bom``, not ``bom nov-26``, so a
product quoted by two paths is one row.

Contracts store a delivery-point name and are resolved at read time through the registry's
aliases, so they need no write. The downgrade does not split the hub again: which rows were
GTF is not kept, and a deleted simulated row is not restored.
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0091_hub_one_identity"
down_revision = "0090_job_progress_steps"
branch_labels = None
depends_on = None

#: A hub's other name -> its registry code (frozen here: a migration does not read the model).
RENAMED = {"GTF": "ETF", "GASPOINT": "ETF", "VTP": "CEGH"}
#: (table, column) holding one hub code.
HUB_COLUMNS = (
    ("market_quotes", "hub"),
    ("market_trades", "hub"),
    ("screen_order_observations", "hub"),
    ("intraday_opportunities", "buy_hub"),
    ("intraday_opportunities", "sell_hub"),
    ("firm_marks", "hub"),
    ("live_market_marks", "hub"),
    ("gas_day_schedule_lines", "hub"),
    ("gas_day_delegations", "hub"),
    ("gas_day_nomination_events", "hub"),
    ("lng_capacity_offers", "hub"),
    ("lng_delivery_obligations", "hub"),
    ("pipeline_supplies", "hub"),
    ("lng_cargo_hedges", "hub"),
    ("lng_terminal_tariff", "hub"),
    ("lng_terminal_terms", "hub"),
    ("storage_facility_masters", "market_hub"),
    ("decision_cases", "hub_id"),
)
#: (table, primary key, column) holding a JSON list of hub codes.
HUB_LISTS = (("trader_mandates", "mandate_id", "hubs"), ("news_items", "item_id", "hubs"))
SIMULATED_SOURCES = ("DEMO_Sim", "EEX_Sim")


def _columns(inspector, table: str) -> set[str]:
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Simulated rows under the other name: the demo's second invented series, deleted.
    for table in ("market_quotes", "market_trades"):
        if "simulated" in _columns(inspector, table):
            bind.execute(
                sa.text(f"DELETE FROM {table} WHERE hub = 'GTF' AND simulated = :yes"),
                {"yes": True},
            )
    if "product" in _columns(inspector, "market_observations"):
        for source in SIMULATED_SOURCES:
            bind.execute(
                sa.text(
                    "DELETE FROM market_observations "
                    "WHERE product LIKE 'GTF %' AND source_system = :source"
                ),
                {"source": source},
            )

    for table, column in HUB_COLUMNS:
        if column not in _columns(inspector, table):
            continue
        for old, new in RENAMED.items():
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),
                {"new": new, "old": old},
            )

    if "hub_code" in _columns(inspector, "reference_market_hubs"):
        held = {code for (code,) in bind.execute(
            sa.text("SELECT hub_code FROM reference_market_hubs"))}
        for old, new in RENAMED.items():
            if old in held and new not in held:
                bind.execute(
                    sa.text("UPDATE reference_market_hubs SET hub_code = :new "
                            "WHERE hub_code = :old"),
                    {"new": new, "old": old},
                )
                held = (held - {old}) | {new}

    for table, key, column in HUB_LISTS:
        if column not in _columns(inspector, table) or key not in _columns(inspector, table):
            continue
        rows = bind.execute(
            sa.text(f"SELECT {key}, {column} FROM {table} WHERE "
                    + " OR ".join(f"CAST({column} AS TEXT) LIKE '%\"{old}\"%'"
                                  for old in RENAMED))
        ).all()
        for row_key, value in rows:
            hubs = json.loads(value) if isinstance(value, str) else value
            if not isinstance(hubs, list):
                continue
            moved = list(dict.fromkeys(RENAMED.get(str(hub).upper(), hub) for hub in hubs))
            if moved != hubs:
                bind.execute(
                    sa.text(f"UPDATE {table} SET {column} = :hubs WHERE {key} = :key")
                    .bindparams(sa.bindparam("hubs", type_=sa.JSON())),
                    {"hubs": moved, "key": row_key},
                )

    observations = _columns(inspector, "market_observations")
    if {"observation_id", "product", "metadata_json"} <= observations:
        rows = bind.execute(
            sa.text("SELECT observation_id, product, metadata_json FROM market_observations "
                    "WHERE product LIKE 'GTF %'")
        ).all()
        for observation_id, product, metadata in rows:
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata = dict(metadata or {})
            if str(metadata.get("hub") or "").upper() == "GTF":
                metadata["hub"] = "ETF"
            bind.execute(
                sa.text("UPDATE market_observations SET product = :product, "
                        "metadata_json = :metadata WHERE observation_id = :id")
                .bindparams(sa.bindparam("metadata", type_=sa.JSON())),
                {"product": "ETF " + product[4:], "metadata": metadata, "id": observation_id},
            )

    # One quote key per product, as every intake stores it.
    if "product" in _columns(inspector, "market_quotes"):
        bind.execute(sa.text(
            "UPDATE market_quotes SET product = 'bom' WHERE product LIKE 'bom %'"))
        bind.execute(sa.text(
            "UPDATE market_quotes SET product = LOWER(product) "
            "WHERE product <> LOWER(product)"))


def downgrade() -> None:
    # Nothing to undo: which rows were written GTF or VTP is not kept, and the old code
    # resolves to the hub the rows now name.
    pass
