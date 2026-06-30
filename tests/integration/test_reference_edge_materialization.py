"""DB-first materialization tests for route candidate map edges."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ReferenceEdge, ReferenceNode, RouteCandidateRecord


def test_materialize_route_candidate_edges_writes_reference_edges(tmp_path) -> None:
    from scripts.ops.materialize_reference_edges import materialize_route_candidate_edges

    db_path = tmp_path / "reference-edge-materialization.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
      session.add_all(
          [
              ReferenceNode(
                  id="entsog-vtp-00002",
                  name="TTF",
                  node_type="hub",
                  country="NL",
                  lat=52.1304,
                  lon=4.8754,
                  source_system="ENTSOG",
                  source_dataset="connectionpoints",
                  source_reference="entsog-connectionpoints",
                  source_record_id="VTP-00002",
                  data_quality="source_metadata",
                  metadata_json={"market_code": "TTF"},
              ),
              ReferenceNode(
                  id="entsog-vtp-00006",
                  name="NBP",
                  node_type="hub",
                  country="GB",
                  lat=53.0316,
                  lon=-0.962,
                  source_system="ENTSOG",
                  source_dataset="connectionpoints",
                  source_reference="entsog-connectionpoints",
                  source_record_id="VTP-00006",
                  data_quality="source_metadata",
                  metadata_json={"market_code": "NBP"},
              ),
              ReferenceNode(
                  id="entsog-itp-gb-bbl",
                  name="Bacton BBL",
                  node_type="interconnection",
                  country="GB",
                  lat=52.85,
                  lon=1.47,
                  source_system="ENTSOG",
                  source_dataset="connectionpoints",
                  source_reference="entsog-connectionpoints",
                  source_record_id="ITP-GB-BBL",
                  data_quality="source_metadata",
                  metadata_json={"point_key": "ITP-GB-BBL"},
              ),
              ReferenceNode(
                  id="entsog-vtp-00016",
                  name="ZTP (Zeebrugge Trading Point H-Zone)",
                  node_type="hub",
                  country="BE",
                  lat=50.9376,
                  lon=4.0204,
                  source_system="ENTSOG",
                  source_dataset="connectionpoints",
                  source_reference="entsog-connectionpoints",
                  source_record_id="VTP-00016",
                  data_quality="source_metadata",
                  metadata_json={},
              ),
              RouteCandidateRecord(
                  route_id="public-route-ttf-bbl-nbp",
                  route_name="TTF -> BBL -> NBP",
                  start_point_name="TTF",
                  target_point_name="NBP",
                  business_model="CROSS_BORDER_TRANSFER",
                  route_legs=[
                      {
                          "leg_id": "bbl-forward",
                          "tso": "BBL Company",
                          "market_area": "BBL",
                          "point_name": "Bacton BBL",
                          "available_capacity_mwh_per_day": 2000.0,
                      }
                  ],
                  required_entry_point_name=None,
                  required_exit_point_name=None,
                  required_tso_access=["BBL Company"],
                  source_systems=["public_route_template", "BBL"],
                  active=True,
                  created_at_utc=now,
              ),
              RouteCandidateRecord(
                  route_id="public-route-nbp-iuk-ztp",
                  route_name="NBP -> IUK -> ZTP",
                  start_point_name="NBP",
                  target_point_name="ZTP",
                  business_model="CROSS_BORDER_TRANSFER",
                  route_legs=[
                      {
                          "leg_id": "iuk-uk-be",
                          "tso": "Interconnector UK",
                          "available_capacity_mwh_per_day": 1500.0,
                      }
                  ],
                  required_entry_point_name="IUK Bacton Entry",
                  required_exit_point_name="IUK Zeebrugge Exit",
                  required_tso_access=["Interconnector UK"],
                  source_systems=["public_route_template", "IUK"],
                  active=True,
                  created_at_utc=now,
              ),
          ]
      )
      session.commit()

    summary = materialize_route_candidate_edges(database_url=database_url)

    assert summary["created_or_updated"] == 3
    with Session(engine) as session:
        edges = session.query(ReferenceEdge).order_by(ReferenceEdge.id).all()

    assert len(edges) == 3
    ttf_bbl_edges = [
        item for item in edges if item.source_record_id == "public-route-ttf-bbl-nbp"
    ]
    assert [(edge.from_node_id, edge.to_node_id) for edge in ttf_bbl_edges] == [
        ("entsog-vtp-00002", "entsog-itp-gb-bbl"),
        ("entsog-itp-gb-bbl", "entsog-vtp-00006"),
    ]
    for sequence, edge in enumerate(ttf_bbl_edges, start=1):
        assert edge.edge_type == "corridor"
        assert edge.source_system == "route_candidate"
        assert edge.metadata_json["materialization"] == "route_candidate_edge"
        assert edge.metadata_json["route_id"] == "public-route-ttf-bbl-nbp"
        assert edge.metadata_json["route_geometry_state"] == "source_derived_leg_sequence"
        assert edge.metadata_json["route_leg_sequence"] == sequence
        assert edge.metadata_json["required_tso_access"] == ["BBL Company"]

    ztp_edge = next(item for item in edges if item.source_record_id == "public-route-nbp-iuk-ztp")
    assert ztp_edge.from_node_id == "entsog-vtp-00006"
    assert ztp_edge.to_node_id == "entsog-vtp-00016"
    assert ztp_edge.metadata_json["required_tso_access"] == ["Interconnector UK"]
