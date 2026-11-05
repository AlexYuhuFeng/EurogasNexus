"""Explicit mathematical boundaries for the supported engines."""


def engine_catalog():
    return [
        {
            "engine": "resource-pool-commercial",
            "scope": "single-day bipartite allocation",
            "constraints": ["per-contract financing", "sale capacity", "TSO access", "currency"],
            "solver": "residual minimum-cost flow",
            "shared_network": False,
        },
        {
            "engine": "resource-pool-phase-two",
            "scope": "single-day separable allocation",
            "constraints": ["minimum take", "resource maximum", "sale capacity", "TSO access"],
            "solver": "bounded-circulation/1",
            "shared_network": False,
        },
        {
            "engine": "joint-network-storage",
            "scope": "multi-day energy-conserving network",
            "constraints": [
                "minimum take/sales",
                "shared edges",
                "inventory continuity",
                "terminal inventory",
                "per-contract financing",
                "confirmed access",
            ],
            "solver": "bounded-circulation/1",
            "shared_network": True,
            "unsupported": [
                "multiplicative losses",
                "stochastic optimization",
                "integer commitments",
            ],
        },
        {
            "engine": "storage-grid",
            "scope": "single-facility dispatch",
            "constraints": ["injection/withdrawal efficiency", "inventory", "terminal inventory"],
            "solver": "inventory-grid dynamic programming",
            "shared_network": False,
        },
    ]
