# 在一台电脑上安装 Eurogas Nexus（小型交易台）

供负责设置交易台服务器电脑的人员（IT 服务台或办公室 IT）阅读，也供需要了解所需设备和步骤的经理
阅读。英文版（权威操作版本）：[SMALL_DESK_INSTALL.md](SMALL_DESK_INSTALL.md)。安装完成后，
把[服务台操作卡](SMALL_DESK_HELPDESK_CARD.md)放在电脑旁边，并把
[交易台应急卡](SMALL_DESK_FALLBACK_CARD-CN.md)交给交易员。

本产品运行在办公室的一台台式电脑上。交易员在自己的 Windows 电脑上通过浏览器（或桌面客户端）打开它。
电脑启动时它会自动启动，每晚自动备份到第二块硬盘，并用简单的话说明哪里有问题
（`sudo nexus status`）。全部工作约一小时，大部分时间用于准备电脑。

## 需要购买的设备

| 设备 | 规格 | 用途 |
| --- | --- | --- |
| 台式电脑 | 8 核处理器，32 GB 内存或以上（最低 16 GB），有线网口 | 运行数据库、应用程序和网页地址 |
| 硬盘 1（固态硬盘） | 1 TB NVMe 固态硬盘 | 操作系统和数据库（速度快） |
| 硬盘 2 | 2 TB 或以上机械硬盘，装在电脑内 | 每晚备份；固态硬盘损坏时数据不丢失 |
| 不间断电源（UPS） | 在线互动式，1000 VA 或以上，带连接电脑的 USB 线 | 短时停电时维持电脑运行，长时停电时让电脑正常关机 |
| 可选 | 办公室网络共享，或由服务台保管的 USB 硬盘 | 在电脑之外再保存一份备份 |

电脑需要：办公室网络中的固定地址（或保留地址），最好在办公室 DNS 中有一个名称（例如
`desk-server`）；可以访问互联网以获取公共市场数据（HTTPS）和时间服务器（NTP）。不需要从办公室
外部访问它。

## 步骤 1：电脑固件（BIOS）

- 把 **"Restore on AC power loss"（断电恢复后）** 设为 **Power On（开机）**，电源恢复后电脑会自动启动。
- 用 USB 线连接 UPS。在步骤 2 中安装 UPS 软件（Ubuntu：`sudo apt install nut`，参见 UPS 厂商
  说明），使电池耗尽前电脑能正常关机。

## 步骤 2：操作系统和 Docker

1. 在固态硬盘上安装 **Ubuntu Server 24.04 LTS**（全部使用默认值；勾选"Install OpenSSH server"，
   便于服务台远程操作）。
2. 时间：`timedatectl` 必须显示 `System clock synchronized: yes`。否则执行
   `sudo timedatectl set-ntp true`（并允许电脑访问办公室时间服务器）。
3. 从 Docker 官方软件源安装 Docker Engine 和 Compose 插件（可免费用于商业用途；按照
   docs.docker.com 上 Ubuntu 的 "Install using the apt repository" 操作），然后
   `sudo docker run --rm hello-world` 必须显示 "Hello from Docker!"。

## 步骤 3：用于备份的第二块硬盘

1. 找到它：`lsblk`（没有分区的 2 TB 硬盘，例如 `sdb`）。
2. 格式化并挂载（把 `sdb` 换成实际名称）：

   ```
   sudo mkfs.ext4 -L nexus-backup /dev/sdb
   sudo mkdir -p /srv/nexus-backup
   echo 'LABEL=nexus-backup /srv/nexus-backup ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
   sudo mount -a && df -h /srv/nexus-backup
   ```

## 步骤 4（可选）：办公室副本

把办公室共享（或 USB 硬盘）挂载到固定目录，例如 `/mnt/nexus-office-copy`，并确保重启后仍然存在
（向 IT 索取该共享的 `fstab` 配置行）。每晚的备份都会复制到这里并校验。

## 步骤 5：安装

把开发人员发来的发布文件夹复制到电脑上（例如用 USB 盘或 `scp`），然后执行：

```
cd eurogas-nexus-small-desk-<版本>
sudo ./nexus install --backup-dir /srv/nexus-backup --server-name desk-server
```

如需办公室副本，加上 `--copy-dir /mnt/nexus-office-copy`。`--server-name` 是电脑在办公室 DNS 中的
名称；再加一次电脑的地址（`--server-name 192.168.1.20`），两者都可以使用。

它按以下顺序执行，并显示结果：

1. **检查电脑**：Docker、内存、两块硬盘的剩余空间、数据库和备份是否在**不同的硬盘**上、时钟是否由
   时间服务器同步、443 端口是否空闲。任何一项不通过就停止并说明怎么做，不做任何更改。
2. 放置发布文件并**生成密钥**（数据库密码、加密密钥）。它们保存在
   `/opt/eurogas-nexus/stack.env`，只有管理员可读，从不显示。
3. 通过受控的数据库升级创建数据库（在固态硬盘上，`/var/lib/eurogas-nexus`），并设置分离的数据库角色。
4. 启动所有部分，并等待每一部分都正常。
5. **创建第一个管理员**（`admin`），并显示一次**一次性密码**。请记下来。
6. 进行第一次备份，设置每晚备份（01:30）和开机自动启动。
7. 最后显示**要打开的地址**以及交易员浏览器需要的证书文件。

如果中途显示 PROBLEM 并停止，请按提示处理，然后再次执行同一条命令：它会从停止的步骤继续。它不会接管
不是由它创建的数据库目录，也不会在已完成的安装上再次运行。

## 步骤 6：交易员的电脑

该地址使用服务器自己的证书。每个交易员的浏览器需要信任它一次：

- 把 `/opt/eurogas-nexus/desk-server-certificate.crt` 复制到交易员的 Windows 电脑。
- 双击它，**安装证书**，**本地计算机**，**将所有证书都放入下列存储**，
  **受信任的根证书颁发机构**，完成。（也可以通过办公室组策略推送到所有电脑。）
- 打开该地址（例如 `https://desk-server`）并加入书签。

## 步骤 7：人员账户

1. 用一次性密码以 `admin` 登录。设置新密码，并在手机上设置身份验证器应用（每个账户都需要第二因素）。
2. 管理，用户：为每位交易员创建一个账户。每人获得一个一次性密码，首次登录时设置自己的身份验证器应用。
3. 管理，数据源：开启交易台使用的公共数据源。

## 步骤 8：离开之前

- `sudo nexus status` 显示 **HEALTHY**（数据源在第一天可能显示"nothing received yet"，即尚未收到数据）。
- 把 `/srv/nexus-backup/nexus-backups/recovery-key.env` 复制到公司的密码保险箱。更换电脑时需要它
  才能读取恢复的数据。
- 打印[服务台操作卡](SMALL_DESK_HELPDESK_CARD.md)。

## 此配置不包含的内容

一台电脑无法保证不间断服务。没有备用电脑，没有公司统一登录，也没有第二个应用进程；产品为较大公司
提供的选项在这里不使用。电脑停止工作时，交易台只用交易屏幕继续工作
（[交易台应急卡](SMALL_DESK_FALLBACK_CARD-CN.md)）。
