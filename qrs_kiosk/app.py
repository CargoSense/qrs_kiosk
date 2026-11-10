"""
The daemon: what a scan does, what the page is told, and the housekeeping
(network status, update checks, the health mark). `run` wires it to the
web server and, on a Pi, the scanner.
"""

import asyncio
import logging
import shutil
import time

import aiohttp
from aiohttp import web

from qrs_kiosk import __version__, qrs, scanner, wifi
from qrs_kiosk.router import route
from qrs_kiosk.updater import Updater

log = logging.getLogger(__name__)

HEALTHY_AFTER = 60
NETWORK_EVERY = 30


class Kiosk:
    def __init__(self, config, http, *, dev=False):
        self.config = config
        self.http = http
        self.dev = dev
        self.clients = set()
        self.shell = {"scanning": False}
        self.scanner = {"connected": dev, "name": "fake scanner (--dev)" if dev else None}
        self.network = {"connected": None, "ssid": None, "ip": None}
        self.want_plate = False
        self.updater = Updater(config, http, config.state_dir)
        self.stopped = asyncio.Event()

    def status(self):
        return {
            "type": "status",
            "version": __version__,
            "name": self.config.get("kiosk", "name"),
            "base": self.config.base,
            "plate": self.config.plate,
            "want_plate": self.want_plate or self.config.plate is None,
            "idle_seconds": self.config.idle_seconds,
            "pin_set": bool(self.config.pin),
            "scanner": self.scanner,
            "network": self.network,
            "update": self.updater.status,
            "dev": self.dev,
        }

    async def broadcast(self, message):
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except (ConnectionError, RuntimeError):
                self.clients.discard(ws)

    async def toast(self, text, kind="info"):
        await self.broadcast({"type": "toast", "text": text, "kind": kind})

    async def navigate(self, url):
        await self.broadcast({"type": "navigate", "url": url})

    async def on_scan(self, scan):
        log.info("scan: %r%s", scan.payload[:120], f" ({scan.symbology})" if scan.symbology else "")
        r = route(
            scan,
            scanning=bool(self.shell.get("scanning")),
            base=self.config.base,
            want_plate=self.want_plate or self.config.plate is None,
        )
        if r.kind == "overlay":
            await self.broadcast({"type": "scan", "payload": scan.payload, "symbology": scan.symbology})
        elif r.kind == "wifi":
            await self.toast(f"Joining {r.wifi.ssid}…")
            ok, message = await wifi.join(r.wifi)
            await self.refresh_network()
            await self.toast(message, "ok" if ok else "error")
        elif r.kind == "command":
            await self.command(r.command)
        elif r.kind == "plate":
            if not await self.set_plate(r.url):
                await self.toast(f"{self.config.base} does not know that sticker", "error")
        elif r.kind == "navigate":
            await self.navigate(r.url)
        else:
            await self.toast("Not a code this terminal knows", "error")

    async def command(self, name):
        if name == "settings":
            await self.navigate("/settings")
        elif name == "set-plate":
            await self.await_plate()
        elif name == "home":
            await self.home()

    async def home(self):
        plate = self.config.plate
        await self.navigate(plate["url"] if plate else "/home")

    async def await_plate(self):
        self.want_plate = True
        await self.toast("Scan the wall plate")
        await self.broadcast(self.status())

    async def set_plate(self, url):
        info = await qrs.describe(url, self.http)
        if info is None:
            return False
        self.config.plate = {"url": url, "label": info["label"], "brand": info["brand"]}
        self.want_plate = False
        log.info("wall plate: %s (%s)", info["label"], url)
        await self.toast(f"Wall plate: {info['label'] or url}", "ok")
        await self.broadcast(self.status())
        await self.navigate(url)
        return True

    async def clear_plate(self):
        self.config.plate = None
        self.want_plate = False
        await self.broadcast(self.status())
        await self.navigate("/home")

    async def on_page_message(self, data):
        kind = data.get("type")
        if kind == "state":
            self.shell = data
        elif kind == "hello":
            await self.broadcast(self.status())
        elif kind == "start":
            if self.config.plate:
                await self.navigate(self.config.plate["url"])
            else:
                await self.toast("Scan the wall plate to start")
        elif kind == "settings":
            await self.navigate("/settings")
        elif kind == "home":
            await self.home()

    async def on_scanner_status(self, status):
        if status != self.scanner:
            self.scanner = status
            await self.broadcast(self.status())

    async def refresh_network(self):
        status = await wifi.status()
        if status != self.network:
            self.network = status
            await self.broadcast(self.status())

    async def apply_update(self):
        if await self.updater.apply():
            await self.toast(f"Updating to {self.updater.status['available']['version']}…", "ok")
            self.stopped.set()
        else:
            await self.broadcast(self.status())

    async def reboot(self):
        await self.toast("Rebooting…")
        if shutil.which("systemctl"):
            await asyncio.create_subprocess_exec("sudo", "-n", "systemctl", "reboot")
        else:
            log.info("reboot requested; no systemctl here")

    async def housekeeping(self):
        started = time.monotonic()
        healthy = False
        last_network = 0
        last_update = 0
        while True:
            now = time.monotonic()
            if not healthy and now - started >= HEALTHY_AFTER:
                self.updater.mark_healthy()
                healthy = True
            if now - last_network >= NETWORK_EVERY:
                last_network = now
                await self.refresh_network()
            every = int(self.config.get("update", "every_minutes")) * 60
            if every > 0 and now - last_update >= every and self.network.get("connected") is not False:
                last_update = now
                await self.updater.check()
                await self.broadcast(self.status())
            await asyncio.sleep(5)


async def run(config, *, dev=False):
    async with aiohttp.ClientSession() as http:
        kiosk = Kiosk(config, http, dev=dev)
        from qrs_kiosk.server import make_app

        runner = web.AppRunner(make_app(kiosk, dev=dev))
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", config.port).start()
        log.info("qrs-kiosk %s on http://localhost:%d (base %s)%s", __version__, config.port, config.base, " [dev]" if dev else "")
        tasks = [asyncio.create_task(kiosk.housekeeping())]
        if not dev:
            tasks.append(asyncio.create_task(scanner.run(config, kiosk.on_scan, kiosk.on_scanner_status)))
        try:
            await kiosk.stopped.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await runner.cleanup()
