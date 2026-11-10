"""
The scanner device, grabbed exclusively so nothing it types reaches the
browser. Finds a device by name, reads it until it goes away, and looks
again. Linux only (evdev); the daemon's --dev mode never calls this.
"""

import asyncio
import logging
import re

from qrs_kiosk.scans import Decoder

log = logging.getLogger(__name__)

RESCAN_SECONDS = 2


def find_device(pattern):
    import evdev

    rx = re.compile(pattern, re.IGNORECASE)
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        keys = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
        if rx.search(dev.name) and evdev.ecodes.KEY_ENTER in keys:
            return dev
        dev.close()
    return None


async def run(config, on_scan, on_status):
    """Reads scans forever. `on_scan(Scan)` and `on_status({connected, name})` are coroutines."""
    while True:
        dev = find_device(config.get("scanner", "match"))
        if dev is None:
            await on_status({"connected": False, "name": None})
            await asyncio.sleep(RESCAN_SECONDS)
            continue
        try:
            await read(dev, config, on_scan, on_status)
        except OSError as e:
            log.info("scanner %s went away: %s", dev.name, e)
        finally:
            try:
                dev.close()
            except OSError:
                pass
        await on_status({"connected": False, "name": None})
        await asyncio.sleep(RESCAN_SECONDS)


async def read(dev, config, on_scan, on_status):
    import evdev

    loop = asyncio.get_running_loop()
    decoder = Decoder(config.get("scanner", "terminator"))
    gap = int(config.get("scanner", "gap_ms")) / 1000
    gone = loop.create_future()
    timer = None

    def deliver(scan):
        if scan:
            asyncio.ensure_future(on_scan(scan))

    def pause():
        deliver(decoder.flush())

    def ready():
        nonlocal timer
        try:
            events = list(dev.read())
        except OSError as e:
            if not gone.done():
                gone.set_exception(e)
            return
        for ev in events:
            if ev.type != evdev.ecodes.EV_KEY:
                continue
            name = evdev.ecodes.KEY.get(ev.code)
            if isinstance(name, list):
                name = name[0]
            deliver(decoder.feed(name, ev.value == 1))
        if timer:
            timer.cancel()
        timer = loop.call_later(gap, pause)

    dev.grab()
    log.info("scanner: %s (%s)", dev.name, dev.path)
    await on_status({"connected": True, "name": dev.name})
    loop.add_reader(dev.fd, ready)
    try:
        await gone
    finally:
        loop.remove_reader(dev.fd)
        if timer:
            timer.cancel()
        try:
            dev.ungrab()
        except OSError:
            pass
