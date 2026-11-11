"""
What a scan means, given where the kiosk is. Pure.

  overlay   the shell has a scan overlay open: hand it over, whatever it is
  wifi      a WiFi QR code: join that network
  command   a `qrs-kiosk:` code: settings, set-plate, home
  plate     a sticker while the kiosk wants a plate: it becomes the plate
  navigate  a sticker under the configured base: show it
  offer     anything else: the shell may take it as the scan its screen
            is waiting for; the page says when nothing did
"""

import re
from dataclasses import dataclass

from qrs_kiosk.scans import Scan
from qrs_kiosk.wifi import parse_wifi_qr

COMMAND_PREFIX = "qrs-kiosk:"
COMMANDS = {"settings", "set-plate", "home"}
STICKER_PATH = re.compile(r"^/s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-z]+/?$")


@dataclass(frozen=True)
class Route:
    kind: str
    scan: Scan | None = None
    url: str | None = None
    command: str | None = None
    wifi: object = None


def sticker_url(text, base):
    """The sticker URL `text` names under `base`, normalised, or None."""
    text = text.strip()
    if not text.startswith(base + "/"):
        return None
    path = text[len(base):]
    if not STICKER_PATH.match(path):
        return None
    return base + path.rstrip("/")


def route(scan, *, scanning, base, want_plate):
    if scanning:
        return Route("overlay", scan=scan)
    wifi = parse_wifi_qr(scan.payload)
    if wifi:
        return Route("wifi", wifi=wifi)
    text = scan.payload.strip()
    if text.startswith(COMMAND_PREFIX):
        name = text[len(COMMAND_PREFIX):].strip().lower()
        return Route("command", command=name) if name in COMMANDS else Route("offer", scan=scan)
    url = sticker_url(text, base)
    if url:
        return Route("plate" if want_plate else "navigate", url=url)
    return Route("offer", scan=scan)
