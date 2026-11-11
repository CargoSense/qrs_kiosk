# qrs_kiosk

The QR Sensor terminal daemon and its page. README.md says what it does
and how to run it; this file says how the code is laid out.

- `qrs_kiosk/app.py` is the daemon: `Kiosk` holds the state (config, the
  shell's last reported state, scanner and network status, the updater) and
  does what a scan means. `run` wires the web server and, on a Pi, the
  scanner. Everything the page is told goes through `broadcast`.
- `router.py` is the pure decision: a scan plus (scanning?, base, want a
  plate?) gives a `Route`. Change behaviour there first and test it there.
- `scans.py` turns key events into a `Scan` (payload, symbology), pure.
  `scanner.py` is the evdev side, Linux only, imported lazily.
- `server.py` is aiohttp: the pages in `web/`, the websocket (`/ws`), the
  settings API (PIN in `x-pin`), and `/dev/scan` in `--dev` mode.
- `web/kiosk.js` is the page: sidebar plus iframe. It does what the daemon
  says (`navigate`, `scan`, `status`, `toast`) and forwards the shell's
  `qrs:state` messages to the daemon. The idle timer lives here.
- `config.py` layers defaults, the provisioning TOML, and `state.json`.
- `updater.py` installs releases; `bin/qrs-kiosk-run` rolls back.
- `image/` and `systemd/` are the Pi install; nothing there runs on a laptop.
- `CHANGELOG.md` gets a line under Unreleased for each change an operator
  or installer would notice; a release moves them under its version.

Messages between page and daemon (JSON over the websocket):

| from | type | fields |
|---|---|---|
| daemon | status | version, name, base, plate, want_plate, idle_seconds, pin_set, scanner, network, update, dev |
| daemon | navigate | url |
| daemon | scan | payload, symbology (for the shell: its open overlay, or the screen's scan button; the shell posts `qrs:unhandled` to the page when neither took it) |
| daemon | toast | text, kind (info, ok, error) |
| page | hello, start, home, settings | |
| page | state | scanning, url, applet, screen (from the shell) |

The shell's side of this is `assets/js/device/kiosk.js` in qrs.

Tests: `uv run pytest`. The server tests drive the daemon through
`/dev/scan` and the websocket with a fake QRS; no network.
