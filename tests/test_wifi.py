from qrs_kiosk.wifi import Wifi, parse_wifi_qr, unescape_fields


def test_the_phone_format():
    assert parse_wifi_qr("WIFI:T:WPA;S:Dock 3;P:s3cret!;;") == Wifi("Dock 3", "s3cret!", "WPA", False)
    assert parse_wifi_qr("WIFI:S:Open;T:nopass;;") == Wifi("Open", "", "NOPASS", False)
    assert parse_wifi_qr("WIFI:T:WPA;S:Hid;P:p;H:true;;") == Wifi("Hid", "p", "WPA", True)


def test_escapes():
    assert parse_wifi_qr(r"WIFI:T:WPA;S:a\;b\:c\\d;P:x\,y;;") == Wifi("a;b:c\\d", "x,y", "WPA", False)


def test_not_wifi():
    assert parse_wifi_qr("https://example.com") is None
    assert parse_wifi_qr("WIFI:T:WPA;P:x;;") is None


def test_nmcli_terse_fields():
    assert unescape_fields(r"wlan0:wifi:connected:Dock\:3") == ["wlan0", "wifi", "connected", "Dock:3"]
