#!/usr/bin/env bash
# Make this Pi's SD card read-only and keep logs (and app data) on a USB stick.
#
# Kept identical in rhb-led-driver and rhb-sensor-monitor; change both.
#
# A power cut mid-write is what corrupts SD cards.  After this script and a
# reboot:
#   /            the SD card, read-only underneath a RAM overlay.  Anything
#                written there vanishes at reboot.
#   /boot        read-only.
#   /data        the USB stick (ext4, label RHBDATA), read-write.
#   /var/log/journal   bind-mounted from /data/journal, so the systemd
#                journal -- every service's stdout/stderr -- is persistent.
#
# If the stick is missing at boot, the Pi still boots (nofail): the journal
# falls back to RAM and the apps fall back to their old paths, in RAM too.
#
# Usage (as root, on the Pi, overlay currently OFF, with internet access in
# case raspi-config needs to install a package):
#
#   sudo scripts/setup-readonly.sh --device /dev/sda1 [--format]
#        [--app NAME --unit UNIT.service] [--no-overlay]
#
#   --device   the USB stick partition.  `lsblk -o NAME,TRAN,SIZE,LABEL` finds it.
#   --format   erase it and make ext4 labeled RHBDATA.  Without this the
#              partition must already carry that label.
#   --app/--unit  create /data/NAME (owned by pi) and give UNIT the
#              environment RHB_DATA_DIR=/data/NAME, for an app that writes
#              its own files.
#   --no-overlay  do everything except turn on the read-only root, e.g. to
#              check the stick setup across a reboot first.
#
# Safe to re-run.  To update code later the overlay must be OFF:
#   sudo raspi-config  ->  Performance Options  ->  Overlay File System  ->  No
# (and say No to the read-only boot partition), reboot, update, turn it back
# on, reboot.

set -euo pipefail

LABEL=RHBDATA
DATA=/data
JOURNAL=/var/log/journal

device="" format=0 app="" unit="" overlay=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --device) device="$2"; shift 2 ;;
        --format) format=1; shift ;;
        --app) app="$2"; shift 2 ;;
        --unit) unit="$2"; shift 2 ;;
        --no-overlay) overlay=0; shift ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

die() { echo "error: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo)"
[[ -n "$device" ]] || die "--device is required"
[[ -b "$device" ]] || die "$device is not a block device"
if [[ -n "$app" && -z "$unit" || -z "$app" && -n "$unit" ]]; then die "--app and --unit go together"; fi
[[ "$(findmnt -no FSTYPE /)" != overlay ]] || die "the overlay is on; turn it off and reboot first (see header)"

# Refuse anything that is not a USB device, or is the boot disk (a Pi can
# boot from USB too): never format the card or drive the system runs from.
disk_of() { local p; p="$(lsblk -no PKNAME "$1" | head -1)"; echo "/dev/${p:-$(basename "$1")}"; }
disk="$(disk_of "$device")"
tran="$(lsblk -dno TRAN "$disk")"
[[ "$tran" == usb ]] || die "$device is on '${tran:-unknown}', not usb"
[[ "$disk" != "$(disk_of "$(findmnt -no SOURCE /)")" ]] || die "$device is on the boot disk"

# --- 1. The stick ----------------------------------------------------------
if [[ $format -eq 1 ]]; then
    lsblk -o NAME,SIZE,LABEL,FSTYPE,MODEL "$disk"
    read -r -p "ERASE everything on $device? Type YES: " answer
    [[ "$answer" == YES ]] || die "not confirmed"
    umount "$device" 2>/dev/null || true
    mkfs.ext4 -F -L "$LABEL" "$device"
fi
[[ "$(blkid -s LABEL -o value "$device")" == "$LABEL" ]] ||
    die "$device is not labeled $LABEL; use --format (erases it)"

# --- 2. Mounts -------------------------------------------------------------
# nofail + a short timeout: a missing stick must never stop the car's Pi booting.
# The bind requires /data, so with no stick it is skipped, not pointed at an
# empty directory on the overlay.
add_fstab() { grep -qF "$1" /etc/fstab || echo "$1" >> /etc/fstab; }
mkdir -p "$DATA" "$JOURNAL"
add_fstab "LABEL=$LABEL $DATA ext4 defaults,noatime,nofail,x-systemd.device-timeout=10s 0 2"
add_fstab "$DATA/journal $JOURNAL none bind,nofail,x-systemd.requires-mounts-for=$DATA 0 0"
systemctl daemon-reload
mountpoint -q "$DATA" || mount "$DATA"
mkdir -p "$DATA/journal"
mountpoint -q "$JOURNAL" || mount "$JOURNAL"
systemd-tmpfiles --create --prefix "$JOURNAL"   # journal ownership and ACLs

# --- 3. journald -----------------------------------------------------------
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/rhb-data.conf <<'EOF'
# Written by setup-readonly.sh.  /var/log/journal is the USB stick.
[Journal]
Storage=persistent
SystemMaxUse=500M
# Default is 5 min; a power cut would lose that much.
SyncIntervalSec=15s
EOF
systemctl restart systemd-journald
journalctl --flush

# --- 4. App data -----------------------------------------------------------
if [[ -n "$app" ]]; then
    mkdir -p "$DATA/$app"
    chown pi:pi "$DATA/$app"
    mkdir -p "/etc/systemd/system/$unit.d"
    cat > "/etc/systemd/system/$unit.d/rhb-data.conf" <<EOF
# Written by setup-readonly.sh.  The app writes its files here (USB stick).
[Unit]
After=data.mount

[Service]
Environment=RHB_DATA_DIR=$DATA/$app
EOF
    systemctl daemon-reload
fi

echo
findmnt "$DATA"
findmnt "$JOURNAL"
journalctl --header | grep -m1 "File path" || true

# --- 5. Read-only root -----------------------------------------------------
if [[ $overlay -eq 1 ]]; then
    for fn in enable_overlayfs enable_bootro; do
        grep -Eq "^$fn ?\(\)" "$(command -v raspi-config)" ||
            die "this raspi-config has no $fn; use its menu: Performance Options -> Overlay File System"
    done
    raspi-config nonint enable_overlayfs
    raspi-config nonint enable_bootro
    echo
    echo "Read-only root enabled.  Reboot to take effect: sudo reboot"
    echo "Afterwards, check:  findmnt /   (FSTYPE overlay)   and   findmnt /data"
else
    echo
    echo "Stick and journal set up; read-only root NOT enabled (--no-overlay)."
fi
