"""Each ``test_*`` demo account copies the demo tester its name implies.

The client shows a person by the job function of the tester they copy
(``clients/web/tests/personFunction.test.ts``); this keeps the copy itself honest.
"""

from __future__ import annotations

from eurogas_nexus.application.local_accounts import DEFAULT_DEMO_TEMPLATES


def test_every_test_account_copies_the_tester_of_the_same_name() -> None:
    assert len(DEFAULT_DEMO_TEMPLATES) >= 9
    for account, template in DEFAULT_DEMO_TEMPLATES.items():
        assert account.startswith("test_"), account
        assert template == "demo." + account.removeprefix("test_").replace("_", "."), account
