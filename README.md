# QR Sensor terminal

A Raspberry Pi with a touchscreen and a barcode scanner, showing QR
Sensor pages. An operator scans a sensor's sticker and works through the
applet on the screen, scanning further codes with the same scanner. A
sidebar stays beside the page: a Start button for the site's wall plate,
where the operator is, and the way into settings.

Two parts:

- `qrs_kiosk/`, a Python daemon. It owns the scanner (grabbed exclusively,
  so nothing it types reaches the browser), decides what each scan means,
  serves the kiosk page and the settings page, keeps the configuration,
  joins WiFi, and updates itself.
- Chromium as a maximized app window showing `http://localhost:4010/`: the sidebar and
  an iframe with the QRS shell. The shell knows it is framed (the kiosk
  bridge in qrs) and takes scans from the page, and tells it where it is.

## What a scan does

| The code | While the shell has a scan overlay open | Otherwise |
|---|---|---|
| anything | handed to the overlay, like its manual entry field | |
| a sticker URL under the configured server | | shown in the frame; the first one while no wall plate is set becomes the plate |
| a WiFi QR code (`WIFI:T:WPA;S:…;P:…;;`) | | joins that network |
| `qrs-kiosk:settings` | | opens settings |
| `qrs-kiosk:set-plate` | | the next sticker scanned becomes the wall plate |
| `qrs-kiosk:home` | | back to the wall plate |
| anything else | | ignored, with a note in the sidebar |

The wall plate is the sticker on the wall that establishes where the
operator is. Start shows its page, which lists the applets for that place.
With nothing happening for `idle_seconds` the frame goes back there.

## Running it on a laptop

```sh
uv sync
cp image/qrs-kiosk.toml.example dev.toml      # set [qrs] base = "http://localhost:4001"
uv run qrs-kiosk --dev --config dev.toml --state dev-state
```

Open http://localhost:4010/. `--dev` adds an endpoint that fakes a scan (the real scanner is read too, where evdev is installed):

```sh
curl -X POST localhost:4010/dev/scan -H 'content-type: application/json' \
  -d '{"payload": "http://localhost:4001/s/<uuid>/<token>"}'
```

The qrs dev config allows `http://localhost:4010` to frame the shell.
Tests: `uv run pytest`.

## The scanner

Any USB or Bluetooth scanner in keyboard (HID) mode works. The daemon finds
it by name (`[scanner] match` in the config, a regular expression) and reads
it until Enter. Two settings on the scanner itself are worth making:

- Send AIM symbology identifiers (`]Q3` before a QR code, `]C1` before Code
  128). The shell's `lengths` rule needs the symbology.
- If any QR code carries newlines (several serials in one code), set the
  scanner to send control characters as Ctrl+key and to end each read with
  Tab or a function key, then set `[scanner] terminator` to match
  (`KEY_TAB`, `KEY_F12`). Otherwise an embedded newline ends the read early.

## Installing on a Pi

Raspberry Pi OS Lite, 64-bit, Trixie. On the Pi, as root, from a checkout:

```sh
sudo sh image/install.sh                 # or: sudo sh image/install.sh qrs_kiosk-<version>-py3-none-any.whl
sudo nano /boot/firmware/qrs-kiosk.toml  # server, WiFi, PIN
sudo reboot
```

The daemon runs as the `kiosk` user under systemd (`qrs-kiosk.service`),
logging to the journal. The same user logs in on tty1 and starts labwc,
whose autostart runs the on-screen keyboard and Chromium. Chromium is a
maximized window with no decorations rather than kiosk mode: a fullscreen
window would sit above the keyboard.

Provisioning before first boot: copy `image/qrs-kiosk.toml.example` to the
SD card's boot partition as `qrs-kiosk.toml` and fill it in. Anything
changed later from the settings page is kept in `/var/lib/qrs-kiosk/` and
wins over that file.

## Settings

Three ways in, in order of how little the device needs:

1. The provisioning file on the boot partition.
2. QR codes scanned with the terminal's scanner: a WiFi code to get online,
   `qrs-kiosk:settings` to open the settings page on the device.
3. The settings page, on the device or from any machine on the same network
   at `http://<device>:4010/settings`. Changes need the PIN from the config.

## Updates

The daemon checks GitHub Releases of this repository every hour (and on
"Check now"), installs a newer wheel into a virtualenv of its own under
`/opt/qrs-kiosk/versions/<version>`, checks that it starts, points
`current` at it and restarts. If the new version fails to come up three
times, `bin/qrs-kiosk-run` points `current` back at `previous`. A version
marks itself healthy after a minute up.

A release is a tag `v<version>` matching `pyproject.toml`; the workflow
builds the wheel and attaches it with `SHA256SUMS`. If the repository is
private, each device needs a token with read access in `[update] token`.

The operating system and Chromium do not update over the air: they come
with the image.

## Not yet verified on hardware

- The labwc session, Chromium under Wayland, and the on-screen keyboard
  (`squeekboard`) appearing when a field in the shell gets focus.
- HaLow: the dongle or HAT needs its vendor's driver, which pins the kernel.
  `install.sh` does not cover it.
