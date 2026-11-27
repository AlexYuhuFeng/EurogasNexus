"""`nexus <command>`: the one entry point for the helpdesk."""

from __future__ import annotations

import argparse
import fcntl
import sys
import time
from pathlib import Path

from nexusctl import operations
from nexusctl.release import ReleaseError
from nexusctl.settings import DEFAULT_ROOT, Settings
from nexusctl.stack import Runner
from nexusctl.ui import Out

BUNDLE = Path(__file__).resolve().parents[1]

HELP = """\
Eurogas Nexus on one PC. Every command needs administrator rights: put sudo in front.

  sudo nexus status              Is everything working? What to do if not.
  sudo nexus start               Start the product (it also starts by itself at boot).
  sudo nexus stop                Stop the product.
  sudo nexus backup              Back up now (it also backs up every night by itself).
  sudo nexus restore             List the backups; `sudo nexus restore <number>` restores one.
  sudo nexus update <folder>     Install the new version in the release folder you were sent.
  sudo nexus undo-update         Go back to the version before the last update.
  sudo nexus diagnostics         Write one file to send to the developers when something is wrong.
  sudo ./nexus install ...       First installation (see the install guide).

Guides: docs/operations/SMALL_DESK_HELPDESK_CARD.md and SMALL_DESK_INSTALL.md.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", add_help=False)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("help")

    install = sub.add_parser("install")
    install.add_argument("--data-dir", type=Path, default=Path("/var/lib/eurogas-nexus"),
                         help="the database folder, on the SSD")
    install.add_argument("--backup-dir", type=Path, required=True,
                         help="the backup folder, on the second disk")
    install.add_argument("--copy-dir", type=Path, default=None,
                         help="an office share or removable disk for a second copy")
    install.add_argument("--server-name", action="append", default=[],
                         help="the PC's name or address on the office network (repeatable)")
    install.add_argument("--https-port", type=int, default=443)
    install.add_argument("--admin-user", default="admin")
    install.add_argument("--backup-time", default="01:30")
    install.add_argument("--bundle", type=Path, default=BUNDLE)
    install.add_argument("--recovery-key", type=Path, default=None,
                         help="recovery-key.env from the old PC (a replaced PC)")
    install.add_argument("--restore-from", type=Path, default=None,
                         help="a backup file to restore after installing (a replaced PC)")
    install.add_argument("--subnet-prefix", default="172.30.58", help=argparse.SUPPRESS)
    install.add_argument("--allow-same-disk", action="store_true", help=argparse.SUPPRESS)
    install.add_argument("--no-systemd", action="store_true", help=argparse.SUPPRESS)
    install.add_argument("--systemd-dir", type=Path, default=Path("/etc/systemd/system"),
                         help=argparse.SUPPRESS)
    install.add_argument("--bin-dir", type=Path, default=Path("/usr/local/bin"),
                         help=argparse.SUPPRESS)
    install.add_argument("--ignore-checks", action="store_true", help=argparse.SUPPRESS)
    # A rehearsal on a small test machine only; a desk server keeps the defaults.
    install.add_argument("--data-min-gb", type=int, default=40, help=argparse.SUPPRESS)
    install.add_argument("--backup-min-gb", type=int, default=100, help=argparse.SUPPRESS)

    start = sub.add_parser("start")
    start.add_argument("--quiet", action="store_true")
    stop = sub.add_parser("stop")
    stop.add_argument("--quiet", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    backup = sub.add_parser("backup")
    backup.add_argument("--scheduled", action="store_true")
    restore = sub.add_parser("restore")
    restore.add_argument("backup", nargs="?", default=None)
    restore.add_argument("--yes", action="store_true")
    update = sub.add_parser("update")
    update.add_argument("bundle", type=Path)
    update.add_argument("--yes", action="store_true")
    update.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    undo = sub.add_parser("undo-update")
    undo.add_argument("--yes", action="store_true")
    diagnostics = sub.add_parser("diagnostics")
    diagnostics.add_argument("--out", type=Path, default=None,
                             help="folder to write to (for example a USB stick)")
    return parser


#: Commands that change the installation: one at a time (the nightly backup never runs in the
#: middle of an update or a restore).
CHANGING = {"start", "stop", "backup", "restore", "update", "undo-update"}


def one_at_a_time(root: Path, *, wait_seconds: float):
    """An exclusive lock on the installation, or None when another command holds it."""

    try:
        handle = (root / ".nexus.lock").open("a")
    except OSError:
        return None
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(10)


def main(argv: list[str] | None = None, *, runner: Runner | None = None, out: Out | None = None):
    args = build_parser().parse_args(argv)
    runner = runner or Runner()
    out = out or Out()
    if args.command in (None, "help"):
        out.line(HELP)
        return 0
    try:
        if args.command == "install":
            settings = Settings(
                root=args.root,
                data_dir=args.data_dir,
                backup_dir=args.backup_dir,
                copy_dir=args.copy_dir,
                server_names=args.server_name or operations.default_server_names(),
                https_port=args.https_port,
                subnet_prefix=args.subnet_prefix,
                backup_time=args.backup_time,
            )
            return operations.install(
                bundle=args.bundle,
                settings=settings,
                runner=runner,
                out=out,
                admin_user=args.admin_user,
                allow_same_disk=args.allow_same_disk,
                systemd_dir=None if args.no_systemd else args.systemd_dir,
                bin_dir=args.bin_dir,
                recovery_key=args.recovery_key,
                restore_from=args.restore_from,
                ignore_checks=args.ignore_checks,
                data_min_gb=args.data_min_gb,
                backup_min_gb=args.backup_min_gb,
            )
        ctx = operations.load_context(args.root, runner, out)
        if args.command in CHANGING:
            scheduled = getattr(args, "scheduled", False)
            lock = one_at_a_time(args.root, wait_seconds=3600 if scheduled else 0)
            if lock is None:
                out.problem(
                    "Another nexus command (a backup, an update or a restore) is running.",
                    "Wait for it to finish, then run this again.",
                )
                return 1
        if args.command == "start":
            return operations.start(ctx, quiet=args.quiet)
        if args.command == "stop":
            return operations.stop(ctx, quiet=args.quiet)
        if args.command == "status":
            return operations.show_status(ctx, as_json=args.json)
        if args.command == "backup":
            return operations.backup(ctx, scheduled=args.scheduled)
        if args.command == "restore":
            return operations.restore(ctx, args.backup, assume_yes=args.yes)
        if args.command == "update":
            return operations.update(ctx, args.bundle, assume_yes=args.yes, force=args.force)
        if args.command == "undo-update":
            return operations.undo_update(ctx, assume_yes=args.yes)
        if args.command == "diagnostics":
            return operations.diagnostics(ctx, args.out)
    except operations.Stop as stop:
        out.problem(str(stop), stop.todo)
        return 1
    except ReleaseError as error:
        out.problem(str(error))
        return 1
    except KeyboardInterrupt:
        out.problem("Interrupted.", "Run `sudo nexus status` to see where things are.")
        return 130
    out.line(HELP)
    return 2


if __name__ == "__main__":
    sys.exit(main())
