"""
The web side: the kiosk page the browser shows, the websocket it talks on,
the settings page and its API, and in --dev mode a way to fake a scan.
Changes through the API need the PIN from the config, when one is set.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from aiohttp import WSMsgType, web

from qrs_kiosk import wifi
from qrs_kiosk.scans import Scan

log = logging.getLogger(__name__)

WEB = Path(__file__).parent / "web"
NO_CACHE = {"cache-control": "no-store"}
KIOSK = web.AppKey("kiosk", object)


def make_app(kiosk, *, dev=False):
    app = web.Application()
    app[KIOSK] = kiosk
    app.router.add_get("/", page("index.html"))
    app.router.add_get("/home", page("home.html"))
    app.router.add_get("/settings", page("settings.html"))
    app.router.add_get("/ws", websocket)
    app.router.add_get("/api/status", get_status)
    app.router.add_post("/api/settings", pinned(post_settings))
    app.router.add_post("/api/plate", pinned(post_plate))
    app.router.add_get("/api/wifi", pinned(get_wifi))
    app.router.add_post("/api/wifi", pinned(post_wifi))
    app.router.add_post("/api/update/check", pinned(post_update_check))
    app.router.add_post("/api/update/apply", pinned(post_update_apply))
    app.router.add_post("/api/reboot", pinned(post_reboot))
    if dev:
        app.router.add_post("/dev/scan", dev_scan)
    app.router.add_static("/static", WEB, show_index=False)
    return app


def page(name):
    async def handler(request):
        return web.FileResponse(WEB / name, headers=NO_CACHE)

    return handler


def pinned(handler):
    async def guarded(request):
        pin = request.app[KIOSK].config.pin
        if pin and request.headers.get("x-pin") != pin:
            return web.json_response({"error": "wrong PIN"}, status=403)
        return await handler(request)

    return guarded


async def body(request):
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def websocket(request):
    kiosk = request.app[KIOSK]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    kiosk.clients.add(ws)
    try:
        await ws.send_json(kiosk.status())
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    await kiosk.on_page_message(data)
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        kiosk.clients.discard(ws)
    return ws


async def get_status(request):
    return web.json_response(request.app[KIOSK].status())


async def post_settings(request):
    kiosk = request.app[KIOSK]
    data = await body(request)
    changed = []
    if "base" in data:
        base = str(data["base"]).strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            return web.json_response({"error": "base must be an http(s) URL"}, status=422)
        kiosk.config.set("qrs", "base", base)
        changed.append("base")
    if "idle_seconds" in data:
        try:
            idle = int(data["idle_seconds"])
        except (TypeError, ValueError):
            return web.json_response({"error": "idle_seconds must be a number"}, status=422)
        if idle < 0:
            return web.json_response({"error": "idle_seconds must be 0 or more"}, status=422)
        kiosk.config.set("kiosk", "idle_seconds", idle)
        changed.append("idle_seconds")
    if "name" in data:
        kiosk.config.set("kiosk", "name", str(data["name"]).strip())
        changed.append("name")
    if "pin" in data:
        new_pin = str(data["pin"]).strip()
        if not re.fullmatch(r"[0-9]{4,8}", new_pin):
            return web.json_response({"error": "the PIN must be 4 to 8 digits"}, status=422)
        kiosk.config.set("kiosk", "pin", new_pin)
        changed.append("pin")
    await kiosk.broadcast(kiosk.status())
    return web.json_response({"changed": changed, "status": kiosk.status()})


async def post_plate(request):
    """{"url": ...} sets the plate, {"url": null} clears it, {"next": true} takes the next sticker scanned."""
    kiosk = request.app[KIOSK]
    data = await body(request)
    if data.get("next"):
        await kiosk.await_plate()
    elif "url" in data:
        if data["url"]:
            ok = await kiosk.set_plate(str(data["url"]).strip())
            if not ok:
                return web.json_response({"error": f"{kiosk.config.base} does not know that sticker"}, status=422)
        else:
            await kiosk.clear_plate()
    return web.json_response(kiosk.status())


async def get_wifi(request):
    return web.json_response({"networks": await wifi.networks(), "status": await wifi.status()})


async def post_wifi(request):
    kiosk = request.app[KIOSK]
    data = await body(request)
    ssid = str(data.get("ssid", "")).strip()
    if not ssid:
        return web.json_response({"error": "ssid is required"}, status=422)
    net = wifi.Wifi(ssid=ssid, password=str(data.get("password", "")), hidden=bool(data.get("hidden")))
    ok, message = await wifi.join(net)
    await kiosk.refresh_network()
    return web.json_response({"ok": ok, "message": message, "network": kiosk.network}, status=200 if ok else 502)


async def post_update_check(request):
    kiosk = request.app[KIOSK]
    await kiosk.updater.check()
    await kiosk.broadcast(kiosk.status())
    return web.json_response(kiosk.updater.status)


async def post_update_apply(request):
    kiosk = request.app[KIOSK]
    if not kiosk.updater.status.get("available"):
        await kiosk.updater.check()
    if not kiosk.updater.status.get("available"):
        return web.json_response({"error": "no update available", **kiosk.updater.status}, status=409)
    asyncio.get_running_loop().create_task(kiosk.apply_update())
    return web.json_response(kiosk.updater.status)


async def post_reboot(request):
    kiosk = request.app[KIOSK]
    await kiosk.reboot()
    return web.json_response({"ok": True})


async def dev_scan(request):
    data = await body(request)
    payload = data.get("payload")
    if not isinstance(payload, str) or not payload:
        return web.json_response({"error": "payload is required"}, status=422)
    await request.app[KIOSK].on_scan(Scan(payload, data.get("symbology")))
    return web.json_response({"ok": True})
