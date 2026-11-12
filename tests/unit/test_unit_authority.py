"""One table of conversion factors: the ontology's. Other modules derive from it."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from eurogas_nexus.domain.market import units as market_units
from eurogas_nexus.domain.ontology import quantity
from eurogas_nexus.domain.ontology.currency import FxTable

SRC = Path(__file__).resolve().parents[2] / "src" / "eurogas_nexus"
ENERGY = ("MWh", "kWh", "GWh", "TWh", "GJ", "therm", "MMBtu")


def _ontology(code: str) -> str:
    return "th" if code == "therm" else code


@pytest.mark.parametrize("source", ENERGY)
@pytest.mark.parametrize("target", ENERGY)
def test_energy_conversions_agree_with_the_ontology(source, target):
    for value in (0.0, 1.0, 29.3071, 1_000_000.0):
        assert market_units.convert_energy(value, source, target) == pytest.approx(
            quantity.convert(value, _ontology(source), _ontology(target)), rel=1e-12
        )


def test_reference_factors_are_the_published_ones():
    # 1 therm = 100,000 Btu(IT) = 29.3071 kWh; 1 MMBtu = 293.071 kWh; 1 MWh = 3.6 GJ.
    assert quantity.convert(1, "th", "kWh") == pytest.approx(29.3071, rel=1e-5)
    assert quantity.convert(1, "MMBtu", "kWh") == pytest.approx(293.071, rel=1e-5)
    assert quantity.convert(1, "MWh", "GJ") == pytest.approx(3.6)
    assert market_units.ENERGY_UNITS_PER_MWH["therm"] == pytest.approx(34.1214, rel=1e-5)


@pytest.mark.parametrize(
    ("source", "target"),
    [("EUR/MWh", "GBp/th"), ("GBp/th", "EUR/MWh"), ("USD/MMBtu", "EUR/MWh"),
     ("EUR/MWh", "USD/MMBtu"), ("EUR/GJ", "GBP/MWh"), ("GBP/MWh", "GBp/th")],
)
def test_price_conversions_agree_with_the_ontology(source, target):
    from datetime import date

    eur_rates = {"GBP": 0.853, "USD": 1.087, "CAD": 1.48}
    fx = FxTable.from_pivot_map(eur_rates, as_of=date(2026, 11, 11), source="test")
    for price in (0.01, 34.65, 112.4):
        ours = market_units.convert_price(price, source, target, eur_rates=eur_rates)
        theirs = quantity.convert_price(price, source, target, fx)
        assert math.isclose(ours, theirs, rel_tol=1e-12), (source, target, price)


def test_no_other_module_writes_its_own_energy_factor():
    """A literal Btu, therm or joule factor outside the ontology is a second table."""

    factors = {
        1055.05585262, 29.3071, 293.071, 293.07107, 105.505585262, 0.293071, 0.0293071,
    }
    offenders = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        if relative in {"domain/ontology/quantity.py", "domain/market/units.py"}:
            continue  # the table, and the module that re-exports its Btu constant
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                if any(math.isclose(node.value, factor, rel_tol=1e-6) for factor in factors):
                    offenders.append(f"{relative}:{node.lineno} {node.value}")
    assert offenders == []
