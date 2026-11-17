"""Valuation inputs: data-quality classes, delivery periods, assumption sets, firm marks
and the valuation snapshot every evaluator reads through.

Pure domain code: no database, no HTTP. The live reader over the runtime store and the
persistence of a snapshot live in ``application/valuation_snapshot.py``.
"""
