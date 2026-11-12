import asyncio
import json

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from qrs_kiosk import app as app_module
from qrs_kiosk.app import Kiosk
from qrs_kiosk.config import Config
from qrs_kiosk.server import make_app

UUID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"


class FakeHttp:
    """Answers the QRS scan JSON for stickers under the fake base."""

    def __init__(self, known):
        self.known = known

    def get(self, url, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def status(self):
        return 200 if self._url in self.known else 404

    def __call__(self, url, **kw):
        self._url = url
        return self

    async def json(self, **kw):
        return self.known[self._url]


class Describing:
    def __init__(self, known):
        self.known = known

    def get(self, url, **kw):
        ctx = FakeHttp(self.known)
        return ctx(url)


@pytest.fixture
async def kiosk(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qrs-kiosk.toml"
    cfg_path.write_text('[qrs]\nbase = "http://qrs.test"\n[kiosk]\npin = "1234"\n')
    config = Config(cfg_path, tmp_path / "state")
    config.load()
    known = {
        f"http://qrs.test/s/{UUID}/plate": {"sensor": {"label": "Monterrey dock"}, "branding": {"name": "Vertiv"}, "applets": []},
    }
    monkeypatch.setattr(app_module.wifi, "status", fake_network_status)
    monkeypatch.setattr(app_module.bluetooth, "status", fake_bluetooth_status)
    k = Kiosk(config, Describing(known), dev=True)
    client = TestClient(TestServer(make_app(k, dev=True)))
    await client.start_server()
    yield k, client
    await client.close()


async def fake_network_status():
    return {"connected": None, "ssid": None, "device": None, "ip": None}


async def fake_bluetooth_status():
    return {"available": False, "paired": []}


async def scan(client, payload, symbology=None):
    res = await client.post("/dev/scan", json={"payload": payload, "symbology": symbology})
    assert res.status == 200


async def messages(ws, n, timeout=2):
    out = []
    for _ in range(n):
        msg = await asyncio.wait_for(ws.receive_json(), timeout)
        out.append(msg)
    return out


async def test_the_first_sticker_becomes_the_plate_and_start_goes_there(kiosk):
    k, client = kiosk
    ws = await client.ws_connect("/ws")
    first = await ws.receive_json()
    assert first["type"] == "status" and first["plate"] is None and first["want_plate"]

    await scan(client, f"http://qrs.test/s/{UUID}/plate")
    got = await messages(ws, 3)
    kinds = [m["type"] for m in got]
    assert kinds == ["toast", "status", "navigate"]
    assert got[1]["plate"] == {"url": f"http://qrs.test/s/{UUID}/plate", "label": "Monterrey dock", "brand": "Vertiv"}
    assert got[2]["url"] == f"http://qrs.test/s/{UUID}/plate"
    assert k.config.plate["label"] == "Monterrey dock"

    await ws.send_json({"type": "start"})
    assert await ws.receive_json() == {"type": "navigate", "url": f"http://qrs.test/s/{UUID}/plate"}
    await ws.close()


async def test_an_unknown_sticker_does_not_become_the_plate(kiosk):
    k, client = kiosk
    ws = await client.ws_connect("/ws")
    await ws.receive_json()
    await scan(client, f"http://qrs.test/s/{UUID}/wrongtoken")
    (toast,) = await messages(ws, 1)
    assert toast["type"] == "toast" and toast["kind"] == "error"
    assert k.config.plate is None
    await ws.close()


async def test_with_a_plate_stickers_navigate_and_overlay_scans_pass_through(kiosk):
    k, client = kiosk
    k.config.plate = {"url": "http://qrs.test/s/x/y", "label": "Dock"}
    ws = await client.ws_connect("/ws")
    await ws.receive_json()

    other = f"http://qrs.test/s/{UUID}/sensor1"
    await scan(client, other)
    assert await ws.receive_json() == {"type": "navigate", "url": other}

    await ws.send_json({"type": "state", "scanning": True})
    await asyncio.sleep(0.05)
    await scan(client, "12345678901234567", "code128")
    assert await ws.receive_json() == {"type": "scan", "payload": "12345678901234567", "symbology": "code128"}

    await ws.send_json({"type": "state", "scanning": False})
    await asyncio.sleep(0.05)
    await scan(client, "12345678901234567")
    assert await ws.receive_json() == {"type": "scan", "payload": "12345678901234567", "symbology": None}, "offered to the shell's screen"
    await ws.close()


async def test_command_codes(kiosk):
    k, client = kiosk
    k.config.plate = {"url": "http://qrs.test/s/x/y", "label": "Dock"}
    ws = await client.ws_connect("/ws")
    await ws.receive_json()
    await scan(client, "qrs-kiosk:settings")
    assert await ws.receive_json() == {"type": "navigate", "url": "/settings"}
    await scan(client, "qrs-kiosk:set-plate")
    got = await messages(ws, 2)
    assert got[0]["type"] == "toast"
    assert got[1]["type"] == "status" and got[1]["want_plate"]
    await scan(client, "qrs-kiosk:home")
    assert await ws.receive_json() == {"type": "navigate", "url": "http://qrs.test/s/x/y"}
    await ws.close()


async def test_settings_need_the_pin(kiosk):
    k, client = kiosk
    res = await client.post("/api/settings", json={"idle_seconds": 10})
    assert res.status == 403
    res = await client.post("/api/settings", json={"idle_seconds": 10, "base": "http://other.test/"}, headers={"x-pin": "1234"})
    assert res.status == 200
    assert k.config.idle_seconds == 10
    assert k.config.base == "http://other.test"
    res = await client.post("/api/settings", json={"base": "ftp://x"}, headers={"x-pin": "1234"})
    assert res.status == 422
    status = await (await client.get("/api/status")).json()
    assert status["idle_seconds"] == 10 and status["pin_set"]


async def test_the_plate_api(kiosk):
    k, client = kiosk
    res = await client.post("/api/plate", json={"url": f"http://qrs.test/s/{UUID}/plate"}, headers={"x-pin": "1234"})
    assert res.status == 200
    assert k.config.plate["label"] == "Monterrey dock"
    res = await client.post("/api/plate", json={"url": "http://qrs.test/s/nope/x"}, headers={"x-pin": "1234"})
    assert res.status == 422
    res = await client.post("/api/plate", json={"url": None}, headers={"x-pin": "1234"})
    assert res.status == 200 and k.config.plate is None


async def test_the_pages_are_served(kiosk):
    k, client = kiosk
    for path in ("/", "/home", "/settings", "/static/kiosk.js", "/static/settings.js", "/static/kiosk.css"):
        res = await client.get(path)
        assert res.status == 200, path


async def test_the_pin_is_four_to_eight_digits(kiosk):
    _, client = kiosk
    for bad in ["12", "abcd", 'vvvv : : :"/<.', "123456789"]:
        res = await client.post("/api/settings", json={"pin": bad}, headers={"x-pin": "1234"})
        assert res.status == 422, bad
    res = await client.post("/api/settings", json={"pin": "246810"}, headers={"x-pin": "1234"})
    assert res.status == 200
    res = await client.post("/api/settings", json={"name": "x"}, headers={"x-pin": "1234"})
    assert res.status == 403
    res = await client.post("/api/settings", json={"name": "x"}, headers={"x-pin": "246810"})
    assert res.status == 200


class Unreachable:
    def get(self, url, **kw):
        raise aiohttp.ClientConnectionError("refused")


async def test_the_page_hears_when_the_server_comes_and_goes(kiosk):
    k, client = kiosk
    ws = await client.ws_connect("/ws")
    first = await ws.receive_json()
    assert first["server"] == {"reachable": None}

    await k.refresh_server()
    (status,) = await messages(ws, 1)
    assert status["type"] == "status" and status["server"] == {"reachable": True}, "a 404 is still an answer"

    k.http = Unreachable()
    await k.refresh_server()
    (status,) = await messages(ws, 1)
    assert status["server"] == {"reachable": False}

    await k.refresh_server()
    with pytest.raises(asyncio.TimeoutError):
        await messages(ws, 1, timeout=0.2)
    await ws.close()


async def test_pairing_a_scanner_needs_the_pin_and_refreshes_status(kiosk, monkeypatch):
    k, client = kiosk
    paired = []

    async def fake_pair(mac):
        paired.append(mac)
        return True, "Paired. Scans should arrive now."

    async def fake_status():
        return {"available": True, "paired": [{"mac": m, "name": "BT Scanner", "connected": True} for m in paired]}

    monkeypatch.setattr(app_module.bluetooth, "pair", fake_pair)
    monkeypatch.setattr(app_module.bluetooth, "status", fake_status)

    res = await client.post("/api/bluetooth/pair", json={"mac": "07:1a:fa:de:72:75"})
    assert res.status == 403

    res = await client.post("/api/bluetooth/pair", json={"mac": "07:1a:fa:de:72:75"}, headers={"x-pin": "1234"})
    assert res.status == 200
    body = await res.json()
    assert paired == ["07:1A:FA:DE:72:75"]
    assert body["bluetooth"]["paired"][0]["connected"]
    assert k.status()["bluetooth"] == body["bluetooth"]


async def test_finding_scanners_without_bluetooth_says_so(kiosk):
    k, client = kiosk
    res = await client.post("/api/bluetooth/scan", headers={"x-pin": "1234"})
    assert res.status == 501
