"""Drain durable functional tasks, including recovery after a web process restart."""

import argparse
import time

from eurogas_nexus.application.functional_runs import run_pending
from eurogas_nexus.db.session import get_session_factory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    options = parser.parse_args()
    if options.interval < 1:
        parser.error("interval must be at least one second")
    factory = get_session_factory()
    while True:
        run_pending(factory)
        if options.once:
            return 0
        time.sleep(options.interval)


if __name__ == "__main__":
    raise SystemExit(main())
