"""The commercial licence gate classifies SPDX expressions fail-closed."""

import pytest

from scripts.security.check_commercial_licenses import evaluate


@pytest.mark.parametrize(
    ("expression", "verdict"),
    [
        ("MIT", "allowed"),
        ("MIT OR Apache-2.0", "allowed"),
        ("Apache-2.0/MIT", "allowed"),
        ("MIT OR Apache-2.0 OR LGPL-2.1-or-later", "allowed"),
        ("BSD-3-Clause AND MIT", "allowed"),
        ("MPL-2.0", "review"),
        ("Mozilla Public License 2.0 (MPL 2.0)", "review"),
        ("GPL-3.0-only", "forbidden"),
        ("AGPL-3.0", "forbidden"),
        ("MIT AND GPL-2.0", "forbidden"),
        ("SSPL-1.0", "forbidden"),
        ("CC-BY-NC-4.0", "forbidden"),
        ("", "unknown"),
        ("NOASSERTION", "unknown"),
        ("Some Custom Licence", "unknown"),
    ],
)
def test_expressions(expression, verdict):
    assert evaluate(expression) == verdict
