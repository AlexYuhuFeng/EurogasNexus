# Eurogas Nexus: what to do when (helpdesk card)

For the IT helpdesk of a desk that runs Eurogas Nexus on one PC. You do not need to know Linux
or Docker. Every action is one command typed on the server PC (or over SSH), starting with
`sudo nexus`. Each command says in plain words what is fine, what is wrong and what to do.

Print this page and keep it next to the server PC.

## First, always

```
sudo nexus status
```

It ends with one of: **HEALTHY**, **WORKING, WITH WARNINGS**, or **PROBLEMS**, then lists each
part with `OK`, `WARNING` or `PROBLEM` and a "What to do" line. Do what it says. If it says to
send diagnostics:

```
sudo nexus diagnostics
```

It writes one `.zip` file and a short `SUMMARY.txt` (it prints both paths). Send the zip to the
developers by email. Every password, key and token is removed from it, so it is safe to send or
to paste the summary into an AI assistant. To put it on a USB stick:
`sudo nexus diagnostics --out /media/<stick name>`.

## It does not start (the traders' browser shows nothing or an error)

1. `sudo nexus status`.
2. If it says "The product is not running": `sudo nexus start`. Wait up to five minutes; it says
   "Every part is running" when done.
3. If a part stays "not running" or "not answering": `sudo nexus stop`, then `sudo nexus start`.
4. Still wrong: `sudo nexus diagnostics` and send the zip. Meanwhile the traders use the desk
   fallback card (they carry on with the trading screen).

If the browser warns that the connection is not private, the trader's PC does not yet trust the
server's certificate: install `desk-server-certificate.crt` on that PC (install guide, step 6).

## The installation stopped halfway

Read the PROBLEM line, do what it says, then run **the same install command again**. It continues
from the step that stopped (it keeps what was already done, including the secrets the database
was made with). Running install on a PC where the installation finished is refused and changes
nothing.

## Removing it

```
sudo nexus uninstall
```

removes the program but keeps the database, the backups and the secrets that open them; running
install again from a release folder brings the desk back with its data. To delete everything,
including the data and the backups on the backup disk (an office copy is not touched):
`sudo nexus uninstall --delete-data`, then type `delete all desk data` when asked.

## It is slow

1. `sudo nexus status`. Look at **Disks** (a nearly full disk slows everything) and **Data
   scheduler**.
2. If nothing is wrong there, ask the traders whether a large report or import is running; it
   finishes by itself.
3. If it stays slow for more than an hour: `sudo nexus diagnostics` and send the zip.

Do not restart the PC during trading hours just because it is slow.

## The disk is full

`sudo nexus status` names the disk:

- **Database disk** (the SSD): send diagnostics; the developers say what can be removed. Do not
  delete files by hand from `/var/lib/eurogas-nexus`.
- **Backup disk** (the second disk): old backups are thinned every night (every night for two
  weeks, then one a week for two months, then one a month for a year). If the disk is still
  full, fit a larger disk, or lower the numbers in `/opt/eurogas-nexus/nexus.conf`
  (`NEXUS_KEEP_DAILY`, `NEXUS_KEEP_WEEKLY`, `NEXUS_KEEP_MONTHLY`). Never delete the newest
  backup.

## The power went out

The server starts by itself when power returns (it is set to, and the uninterruptible power
supply gives it time to stop cleanly). After power returns:

1. Wait five minutes, then `sudo nexus status`.
2. If it is not HEALTHY: `sudo nexus start`, then check again.
3. If the database will not start: `sudo nexus diagnostics` and send the zip. Do not restore a
   backup unless the developers ask you to.

If the PC does not start on its own after a power cut, set "restore on AC power loss" to "power
on" in the PC's BIOS (install guide, step 1).

## A backup failed, or "No backup in the last day"

1. `sudo nexus backup`. It ends with "Backup written and verified" when it worked.
2. If it says the office or removable copy failed: check the office share or the USB disk is
   connected. The backup on the second disk is still good.
3. If the backup itself fails: `sudo nexus diagnostics` and send the zip.

## The PC was replaced (or its SSD failed)

You need: the release folder (from the developers), the **backup disk** or the office copy of
the backups, and the **recovery key file** (`recovery-key.env`, kept in the firm's password
safe when the PC was installed).

1. Prepare the new PC as in the install guide (steps 1 to 4).
2. Fit the old backup disk (or copy the office copy onto the new backup disk).
3. From the release folder:

   ```
   sudo ./nexus install --backup-dir /srv/nexus-backup \
       --recovery-key /path/to/recovery-key.env \
       --restore-from /srv/nexus-backup/nexus-backups/<newest .dump file>
   ```

4. `sudo nexus status`. People sign in with their usual passwords and authenticator apps.

Without the recovery key the data is restored, but every person must set up their
authenticator app again and the stored data-provider keys must be entered again
(Admin, Data sources).

## Updating to a new version

The developers send a release folder. Copy it to the server, then from inside it:

```
sudo nexus update .
```

It backs up first, installs, checks the result and, if the new version is not healthy, goes
back to the old one by itself. If the traders find a problem after an update:

```
sudo nexus undo-update
```

It says before it starts whether anything entered since the update will be lost (only when the
update made a database change that cannot be undone; that data is then kept in a backup file).

## Restoring a backup (only when the developers ask)

```
sudo nexus restore            (lists the backups, newest first)
sudo nexus restore 3          (restores number 3 from the list)
```

The current data is backed up first and the replaced database is kept until the next restore.

## Commands

| Command | What it does |
| --- | --- |
| `sudo nexus status` | Is everything working; what to do if not |
| `sudo nexus start` / `stop` | Start or stop the product (it starts by itself at boot) |
| `sudo nexus backup` | Back up now (it also runs every night) |
| `sudo nexus restore [number]` | List backups, or restore one |
| `sudo nexus update <folder>` | Install a new version (backs up first, undoes itself on failure) |
| `sudo nexus undo-update` | Return to the version before the last update |
| `sudo nexus diagnostics` | One file to send to the developers |
| `sudo nexus uninstall` | Remove the program, keep the data and backups (`--delete-data` removes them too) |

Where things are: the program and settings in `/opt/eurogas-nexus`; the database on the SSD in
`/var/lib/eurogas-nexus`; backups on the second disk in `<backup folder>/nexus-backups`.
