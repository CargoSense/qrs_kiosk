from qrs_kiosk.router import Route, route, sticker_url
from qrs_kiosk.scans import Scan

BASE = "https://app.qrsensor.com"
URL = f"{BASE}/s/0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0/1k2j3h4g"


def go(payload, **kw):
    args = {"scanning": False, "base": BASE, "want_plate": False}
    args.update(kw)
    return route(Scan(payload), **args)


def test_sticker_urls_under_the_base():
    assert sticker_url(URL, BASE) == URL
    assert sticker_url(URL + "/", BASE) == URL
    assert sticker_url(" " + URL + "\n", BASE) == URL
    assert sticker_url(URL.replace("app.qrsensor.com", "staging.qrsensor.com"), BASE) is None
    assert sticker_url(f"{BASE}/s/not-a-uuid/tok", BASE) is None
    assert sticker_url(f"{BASE}/s/0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0/tok/scan_delivery_box", BASE) is None
    assert sticker_url(f"{BASE}/api/v0/sensors", BASE) is None


def test_a_sticker_navigates_or_becomes_the_plate():
    assert go(URL) == Route("navigate", url=URL)
    assert go(URL, want_plate=True) == Route("plate", url=URL)


def test_anything_goes_to_an_open_overlay():
    for payload in (URL, "ABC123", "WIFI:S:x;P:y;;", "qrs-kiosk:settings"):
        r = go(payload, scanning=True)
        assert r.kind == "overlay"
        assert r.scan.payload == payload


def test_wifi_and_commands():
    r = go("WIFI:T:WPA;S:Dock;P:secret;;")
    assert r.kind == "wifi"
    assert r.wifi.ssid == "Dock"
    assert go("qrs-kiosk:settings").command == "settings"
    assert go("QRS-KIOSK:Set-Plate".lower()).command == "set-plate"
    assert go("qrs-kiosk:format-disk").kind == "offer"


def test_other_codes_are_offered_to_the_shell():
    r = go("12345678901234567")
    assert r.kind == "offer" and r.scan.payload == "12345678901234567"
    assert go("https://example.com/s/0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0/tok").kind == "offer"
