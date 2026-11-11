#!/bin/sh
# Turns a fresh Raspberry Pi OS Lite (Trixie, 64-bit) into a QR Sensor
# terminal. Run as root on the Pi, from a checkout or a downloaded copy:
#
#   sudo sh install.sh [path/to/qrs_kiosk-<version>-py3-none-any.whl]
#
# Without a wheel it installs the checkout this script is in.
set -eu

root=/opt/qrs-kiosk
state=/var/lib/qrs-kiosk
user=kiosk
here=$(cd "$(dirname "$0")/.." && pwd)
wheel=${1:-}

echo "== packages"
apt-get update
apt-get install -y --no-install-recommends \
  labwc seatd wlr-randr chromium squeekboard \
  network-manager fonts-dejavu-core curl ca-certificates

echo "== user $user"
id "$user" >/dev/null 2>&1 || useradd -m -s /bin/bash "$user"
usermod -aG input,netdev,video,render,audio "$user"

echo "== uv"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh
fi

echo "== daemon"
mkdir -p "$root/versions" "$root/bin" "$state"
if [ -n "$wheel" ]; then
  version=$(basename "$wheel" | sed -E 's/^qrs_kiosk-([^-]+)-.*/\1/')
  spec="qrs-kiosk[pi] @ file://$(cd "$(dirname "$wheel")" && pwd)/$(basename "$wheel")"
else
  version=$(grep -E '^version' "$here/pyproject.toml" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
  spec="$here[pi]"
fi
target="$root/versions/$version"
rm -rf "$target"
uv venv --quiet "$target"
uv pip install --quiet --python "$target/bin/python" "$spec"
ln -sfn "$target" "$root/current"
cp "$here/bin/qrs-kiosk-run" "$here/bin/qrs-kiosk-browser" "$root/bin/"
chmod +x "$root/bin/"*
chown -R "$user:$user" "$root" "$state"

echo "== config"
[ -f /boot/firmware/qrs-kiosk.toml ] || cp "$here/image/qrs-kiosk.toml.example" /boot/firmware/qrs-kiosk.toml

echo "== services"
cp "$here/systemd/qrs-kiosk.service" /etc/systemd/system/
cat > /etc/sudoers.d/qrs-kiosk <<SUDO
$user ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
SUDO
chmod 440 /etc/sudoers.d/qrs-kiosk
systemctl daemon-reload
systemctl enable qrs-kiosk

echo "== wifi from the provisioning file"
"$target/bin/python" - <<PY
import subprocess, tomllib
cfg = tomllib.load(open("/boot/firmware/qrs-kiosk.toml", "rb"))
w = cfg.get("wifi", {})
if w.get("ssid"):
    args = ["nmcli", "device", "wifi", "connect", w["ssid"]]
    if w.get("password"): args += ["password", w["password"]]
    if w.get("hidden"): args += ["hidden", "yes"]
    subprocess.run(args, check=False)
PY

echo "== kiosk session"
home=$(eval echo "~$user")
mkdir -p "$home/.config/labwc"
cp "$here/image/labwc-autostart" "$home/.config/labwc/autostart"
mkdir -p "$home/.local/share/squeekboard/keyboards"
cp "$here/image/squeekboard/us_wide.yaml" "$home/.local/share/squeekboard/keyboards/"
cat > "$home/.config/labwc/rc.xml" <<'RC'
<?xml version="1.0"?>
<labwc_config>
  <core><gap>0</gap></core>
  <theme><cornerRadius>0</cornerRadius></theme>
  <touch mapToOutput="DSI-1" mouseEmulation="no"/>
  <windowRules>
    <windowRule identifier="*" serverDecoration="no"><action name="Maximize"/></windowRule>
  </windowRules>
</labwc_config>
RC
cat > "$home/.config/labwc/environment" <<'ENV'
XKB_DEFAULT_LAYOUT=us
ENV
cat > "$home/.profile" <<'PROFILE'
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = /dev/tty1 ]; then
  exec labwc
fi
PROFILE
chown -R "$user:$user" "$home"
if command -v raspi-config >/dev/null; then
  raspi-config nonint do_boot_behaviour B2
  sed -i "s/--autologin [a-z]*/--autologin $user/" /etc/systemd/system/getty@tty1.service.d/autologin.conf 2>/dev/null || true
fi

echo "== done: reboot to start the terminal"
