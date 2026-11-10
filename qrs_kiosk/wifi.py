"""
Networks. A WiFi QR code is the one phones make (`WIFI:T:WPA;S:ssid;P:pass;;`);
scanning one joins that network, which is how a device with no keyboard gets
online. Joining and status go through NetworkManager's nmcli; where it is
missing (a laptop) status says so and joining fails gracefully.
"""

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Wifi:
    ssid: str
    password: str = ""
    security: str = "WPA"
    hidden: bool = False


def parse_wifi_qr(text):
    text = text.strip()
    if not text.upper().startswith("WIFI:"):
        return None
    fields = {}
    key = None
    buf = []
    i = 5
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            buf.append(text[i + 1])
            i += 2
            continue
        if key is None:
            if c == ":":
                key = "".join(buf).upper()
                buf = []
            else:
                buf.append(c)
        elif c == ";":
            fields[key] = "".join(buf)
            key = None
            buf = []
        else:
            buf.append(c)
        i += 1
    ssid = fields.get("S", "")
    if not ssid:
        return None
    security = fields.get("T", "WPA").upper() or "nopass"
    return Wifi(
        ssid=ssid,
        password=fields.get("P", "") if security != "NOPASS" else "",
        security=security,
        hidden=fields.get("H", "").lower() == "true",
    )


async def nmcli(*args, timeout=60):
    if not shutil.which("nmcli"):
        return None, "nmcli is not installed"
    proc = await asyncio.create_subprocess_exec(
        "nmcli", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None, "nmcli timed out"
    text = out.decode(errors="replace").strip()
    return proc.returncode, text


async def join(wifi):
    """Joins the network. Returns (ok, message)."""
    args = ["device", "wifi", "connect", wifi.ssid]
    if wifi.password:
        args += ["password", wifi.password]
    if wifi.hidden:
        args += ["hidden", "yes"]
    code, text = await nmcli(*args, timeout=90)
    if code == 0:
        log.info("joined %s", wifi.ssid)
        return True, f"Joined {wifi.ssid}"
    log.warning("could not join %s: %s", wifi.ssid, text)
    return False, text or "could not join"


async def networks():
    """Networks in range: [{ssid, signal, security}], strongest first."""
    code, text = await nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes")
    if code != 0:
        return []
    seen = {}
    for line in text.splitlines():
        parts = unescape_fields(line)
        if len(parts) < 3 or not parts[0]:
            continue
        ssid, signal, security = parts[0], int(parts[1] or 0), parts[2]
        if ssid not in seen or seen[ssid]["signal"] < signal:
            seen[ssid] = {"ssid": ssid, "signal": signal, "security": security}
    return sorted(seen.values(), key=lambda n: -n["signal"])


async def status():
    """{"connected": bool|None, "ssid", "device", "ip"}; connected None when nmcli is missing."""
    code, text = await nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
    if code is None:
        return {"connected": None, "ssid": None, "device": None, "ip": None, "note": text}
    if code != 0:
        return {"connected": False, "ssid": None, "device": None, "ip": None, "note": text}
    for line in text.splitlines():
        parts = unescape_fields(line)
        if len(parts) >= 4 and parts[2] == "connected" and parts[1] != "loopback":
            device, conn = parts[0], parts[3]
            return {"connected": True, "ssid": conn, "device": device, "ip": await address(device)}
    return {"connected": False, "ssid": None, "device": None, "ip": None}


async def address(device):
    code, text = await nmcli("-t", "-f", "IP4.ADDRESS", "device", "show", device)
    if code != 0:
        return None
    m = re.search(r":([\d.]+)/", text)
    return m.group(1) if m else None


def unescape_fields(line):
    """nmcli -t escapes ':' in values as '\\:'."""
    fields, buf, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if c == ":":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    fields.append("".join(buf))
    return fields
