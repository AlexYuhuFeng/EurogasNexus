# Installing Eurogas Nexus on one PC (small desk)

For the person who sets up the desk's server PC (the helpdesk, or IT for the office). Chinese
version: [SMALL_DESK_INSTALL-CN.md](SMALL_DESK_INSTALL-CN.md). After installation, keep the
[helpdesk card](SMALL_DESK_HELPDESK_CARD.md) next to the PC and give the traders the
[desk fallback card](SMALL_DESK_FALLBACK_CARD.md).

The product runs on one desktop PC in the office. The traders open it in their browser (or the
desktop client) on their own Windows PCs. It starts by itself when the PC starts, backs itself
up every night to a second disk, and says in plain words what is wrong (`sudo nexus status`).
About one hour of work, most of it preparing the PC.

## What to buy

| Item | What | Why |
| --- | --- | --- |
| Desktop PC | 8 processor cores, 32 GB memory or more (16 GB is the minimum), wired network port | Runs the database, the application and the web address |
| Disk 1 (SSD) | 1 TB NVMe SSD | The operating system and the database (fast) |
| Disk 2 | 2 TB or larger hard disk, inside the PC | The nightly backups; if the SSD fails, nothing is lost |
| Uninterruptible power supply (UPS) | Line-interactive, 1000 VA or more, with a USB cable to the PC | Keeps the PC running through short cuts and lets it stop cleanly in a long one |
| Optional | An office network share, or a USB disk kept by the helpdesk | A second copy of each backup outside the PC |

The PC needs: a fixed address on the office network (or a reserved one) and, ideally, a name in
the office DNS (for example `desk-server`); outbound internet access for the public market data
(HTTPS) and a time server (NTP). It needs no inbound access from outside the office.

## Step 1: the PC's firmware (BIOS)

- Set **"Restore on AC power loss"** (or "After power failure") to **Power On**, so the PC starts
  by itself when power returns.
- Connect the UPS by USB. In step 2, install the UPS software (Ubuntu: `sudo apt install nut`;
  your UPS vendor's guide) so the PC shuts down cleanly before the battery runs out.

## Step 2: the operating system and Docker

1. Install **Ubuntu Server 24.04 LTS** on the SSD (all defaults; tick "Install OpenSSH server" so
   the helpdesk can work remotely). Note the user name and password you choose.
2. Time: `timedatectl` must show `System clock synchronized: yes`. If not:
   `sudo timedatectl set-ntp true` (and allow the PC to reach the office time server).
3. Docker Engine with the Compose plugin, from Docker's own package source (free for commercial
   use; follow "Install using the apt repository" on docs.docker.com for Ubuntu), then
   `sudo docker run --rm hello-world` must print "Hello from Docker!".

## Step 3: the second disk for backups

1. Find it: `lsblk` (the 2 TB disk without partitions, for example `sdb`).
2. Format and mount it (replace `sdb`):

   ```
   sudo mkfs.ext4 -L nexus-backup /dev/sdb
   sudo mkdir -p /srv/nexus-backup
   echo 'LABEL=nexus-backup /srv/nexus-backup ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
   sudo mount -a && df -h /srv/nexus-backup
   ```

## Step 4 (optional): the office copy

Mount the office share (or plug in the USB disk) at a fixed folder, for example
`/mnt/nexus-office-copy`, so it is there after a restart (ask IT for the share's `fstab` line).
Each nightly backup is copied there and checked.

## Step 5: install

Copy the release folder you received from the developers to the PC (for example with a USB
stick or `scp`), then:

```
cd eurogas-nexus-small-desk-<version>
sudo ./nexus install --backup-dir /srv/nexus-backup --server-name desk-server
```

Add `--copy-dir /mnt/nexus-office-copy` for the office copy. `--server-name` is the PC's name
in the office DNS; repeat it for the PC's address (`--server-name 192.168.1.20`) so both work.

What it does, in this order, and what it prints:

1. **Checks the PC**: Docker, memory, free space on both disks, that the database and the
   backups are on **different disks**, that the clock is kept by a time server, that port 443 is
   free. If anything fails it stops and says what to do; nothing is changed.
2. Puts the release in place and **creates the secrets** (database passwords, the encryption
   key). They are kept in `/opt/eurogas-nexus/stack.env`, readable only by the administrator,
   and never printed.
3. Creates the database (on the SSD, `/var/lib/eurogas-nexus`) with the gated database upgrade
   and separate database roles.
4. Starts every part and waits until each is healthy.
5. **Creates the first administrator** (`admin`) and prints a **one-time password**, once.
   Write it down.
6. Takes the first backup, sets up the nightly backup (01:30) and starting at boot.
7. Ends with the **address to open** and the certificate file for the traders' browsers.

## Step 6: the traders' PCs

The address uses the server's own certificate. Each trader's browser must trust it once:

- Copy `/opt/eurogas-nexus/desk-server-certificate.crt` to the trader's Windows PC.
- Double-click it, **Install Certificate**, **Local Machine**, **Place all certificates in the
  following store**, **Trusted Root Certification Authorities**, Finish. (Or push it to all PCs
  with the office's group policy.)
- Open the address (for example `https://desk-server`) and bookmark it.

## Step 7: people

1. Sign in as `admin` with the one-time password. Choose a new password and set up an
   authenticator app on your phone (every account needs a second factor).
2. Admin, Users: create one account per trader. Each gets a one-time password and sets up their
   own authenticator app at first sign-in.
3. Admin, Data sources: switch on the public sources the desk uses.

## Step 8: before you leave

- `sudo nexus status` shows **HEALTHY** (data sources may show "nothing received yet" for a day).
- Copy `/srv/nexus-backup/nexus-backups/recovery-key.env` into the firm's password safe. A
  replacement PC needs it to read the restored data.
- Print the [helpdesk card](SMALL_DESK_HELPDESK_CARD.md).

## What is not in this setup

One PC cannot promise uninterrupted service. There is no standby PC, no company single sign-on
and no second application process; the product's larger-firm options are not used here. When
the PC is down, the desk carries on with the trading screen alone
([desk fallback card](SMALL_DESK_FALLBACK_CARD.md)).
