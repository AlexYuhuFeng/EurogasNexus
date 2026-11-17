"""Local accounts from the server's shell (headless installs, the first administrator).

Runs against the runtime database configured for the API (``RUNTIME_STORE_DATABASE_URL``)
and uses the same code path as Admin -> Users, so the same policy, storage and audit apply::

    python -m eurogas_nexus.cli.accounts create --username alice --display-name "Alice" --admin
    python -m eurogas_nexus.cli.accounts reset-password --username alice
    python -m eurogas_nexus.cli.accounts list

``create`` and ``reset-password`` print a one-time temporary password exactly once, to this
terminal only (it is never logged or audited). The person signs in with it and must choose
their own password. The audit trail records the actor as ``cli:<operating-system user>``.
"""

from __future__ import annotations

import argparse
import getpass
import sys


def _actor() -> str:
    try:
        return f"cli:{getpass.getuser()}"[:80]
    except Exception:  # noqa: BLE001 - no login name in a container is fine
        return "cli:operator"


def _session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise SystemExit("RUNTIME_STORE_DATABASE_URL is not set: point it at the runtime database")
    return get_session_factory()()


def _find(session, username: str):
    from eurogas_nexus.db.models import IdentityPrincipalRecord

    row = (
        session.query(IdentityPrincipalRecord)
        .filter(IdentityPrincipalRecord.name == username)
        .one_or_none()
    )
    if row is None:
        raise SystemExit(f"no user named {username!r}")
    return row


def main(argv: list[str] | None = None) -> int:
    from eurogas_nexus.application import local_accounts

    parser = argparse.ArgumentParser(prog="python -m eurogas_nexus.cli.accounts")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create a local account")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", default="")
    create.add_argument("--email", default=None)
    create.add_argument("--role", action="append", default=[], help="repeatable; VIEWER default")
    create.add_argument("--admin", action="store_true", help="grant the ADMIN role")
    create.add_argument("--scope", action="append", default=[], help="data scope (repeatable)")
    reset = commands.add_parser("reset-password", help="issue a new one-time password")
    reset.add_argument("--username", required=True)
    commands.add_parser("list", help="list people and their account state")
    args = parser.parse_args(argv)

    with _session() as session:
        try:
            if args.command == "create":
                roles = [r.upper() for r in args.role] + (["ADMIN"] if args.admin else [])
                row, secret = local_accounts.create_local_account(
                    session,
                    username=args.username,
                    display_name=args.display_name,
                    email=args.email,
                    grants=local_accounts.AccountGrants(
                        roles=tuple(roles or ["VIEWER"]),
                        data_scopes=tuple(args.scope),
                        job_functions=("PLATFORM_ADMINISTRATOR",) if args.admin else (),
                    ),
                    actor=_actor(),
                )
                session.commit()
                print(f"created {row.name} ({', '.join(row.roles or [row.role])})")
                print(f"one-time password (shown once): {secret}")
                print("The person signs in with it and must choose their own password.")
            elif args.command == "reset-password":
                row = _find(session, args.username)
                secret = local_accounts.reset_password(
                    session, row.principal_id, actor=_actor()
                )
                session.commit()
                print(f"one-time password for {row.name} (shown once): {secret}")
            else:
                from eurogas_nexus.db.repositories.identity import list_identity_principals

                for item in list_identity_principals(session):
                    print(
                        f"{item['name']:<28} {item['account_kind']:<8} "
                        f"{item['account_state']:<9} {','.join(item['roles'])}"
                    )
        except local_accounts.LocalAccountError as exc:
            session.rollback()
            print(f"refused: {exc.message} ({exc.code})", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
