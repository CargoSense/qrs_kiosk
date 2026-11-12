"""
The Bluetooth scanner's bond with the terminal, for the day it is lost and
nobody at the dock has a keyboard. Everything goes through bluetoothctl in
its one-shot mode, as the kiosk user: BlueZ's D-Bus policy lets any user
talk to it. Where bluetoothctl is missing (a laptop) status says so and
pairing fails gracefully.
"""

import asyncio
import logging
import re
import shutil

log = logging.getLogger(__name__)

SCAN_SECONDS = 12
ANSI = re.compile(r"\x1b\[[0-9;]*m")
DEVICE = re.compile(r"^Device ([0-9A-F]{2}(?::[0-9A-F]{2}){5}) (.+)$")
MAC = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


async def bluetoothctl(*args, timeout=30):
    if not shutil.which("bluetoothctl"):
        return None, "bluetoothctl is not installed"
    proc = await asyncio.create_subprocess_exec(
        "bluetoothctl",
        "--agent",
        "NoInputNoOutput",
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None, "bluetoothctl timed out"
    return proc.returncode, ANSI.sub("", out.decode(errors="replace")).strip()


def parse_devices(text):
    """`Device MAC Name` lines → [{mac, name}]. A device with no name is listed by its address and left out."""
    found = []
    for line in text.splitlines():
        m = DEVICE.match(line.strip())
        if not m:
            continue
        mac, name = m.group(1), m.group(2).strip()
        if name == mac.replace(":", "-"):
            continue
        found.append({"mac": mac, "name": name})
    return found


async def listed(prop=None):
    code, text = await bluetoothctl("devices", *([prop] if prop else []))
    return parse_devices(text) if code == 0 else []


async def status():
    """{"available": bool, "paired": [{mac, name, connected}]}; available False when bluetoothctl is missing."""
    code, text = await bluetoothctl("devices", "Paired")
    if code is None:
        return {"available": False, "paired": [], "note": text}
    if code != 0:
        return {"available": False, "paired": [], "note": text or "bluetoothctl failed"}
    connected = {d["mac"] for d in await listed("Connected")}
    return {
        "available": True,
        "paired": [{**d, "connected": d["mac"] in connected} for d in parse_devices(text)],
    }


async def discover(match):
    """Looks for SCAN_SECONDS, then lists every named device in reach: [{mac, name, paired, scanner}], likely scanners first."""
    await bluetoothctl("--timeout", str(SCAN_SECONDS), "scan", "on", timeout=SCAN_SECONDS + 15)
    paired = {d["mac"] for d in await listed("Paired")}
    rx = re.compile(match, re.IGNORECASE)
    devices = [
        {**d, "paired": d["mac"] in paired, "scanner": bool(rx.search(d["name"]))} for d in await listed()
    ]
    return sorted(devices, key=lambda d: (not d["scanner"], d["name"].lower()))


async def pair(mac):
    """Pairs, trusts and connects the device, dropping any bond the terminal already holds for it. Returns (ok, message)."""
    # With the adapter not pairable the kernel answers "no bonding" and the
    # key is never stored; the HID profile then refuses the scanner.
    if not MAC.match(mac):
        return False, "that is not a Bluetooth address"
    if any(d["mac"] == mac for d in await listed("Paired")):
        await bluetoothctl("remove", mac)
    await bluetoothctl("pairable", "on")
    try:
        for verb in ("pair", "trust", "connect"):
            code, text = await bluetoothctl(verb, mac, timeout=60)
            if code is None:
                return False, text
            if code != 0 or "Failed" in text:
                log.warning("could not %s %s: %s", verb, mac, text)
                return False, failure(text) or f"could not {verb}"
    finally:
        await bluetoothctl("pairable", "off")
    log.info("paired scanner %s", mac)
    return True, "Paired. Scans should arrive now."


async def forget(mac):
    """Returns (ok, message)."""
    if not MAC.match(mac):
        return False, "that is not a Bluetooth address"
    code, text = await bluetoothctl("remove", mac)
    if code is None:
        return False, text
    if code != 0 or "Failed" in text:
        return False, failure(text) or "could not forget it"
    log.info("forgot %s", mac)
    return True, "Forgotten."


def failure(text):
    """The `Failed to ...: org.bluez.Error.X` line, as a few words."""
    for line in text.splitlines():
        if line.startswith("Failed"):
            return line.replace("org.bluez.Error.", "")
    return None
