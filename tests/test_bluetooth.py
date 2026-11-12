import pytest

from qrs_kiosk import bluetooth

LISTING = """Device 07:1A:FA:DE:72:75 BT Scanner HID_7275
Device 60:90:B9:29:02:8D 60-90-B9-29-02-8D
Device B8:B4:09:FA:86:D3 HART Right 85
"""


def test_devices_with_no_name_are_left_out():
    assert bluetooth.parse_devices(LISTING) == [
        {"mac": "07:1A:FA:DE:72:75", "name": "BT Scanner HID_7275"},
        {"mac": "B8:B4:09:FA:86:D3", "name": "HART Right 85"},
    ]


def test_the_failure_line():
    assert bluetooth.failure("Attempting to pair with 07:1A:FA:DE:72:75\nFailed to pair: org.bluez.Error.AuthenticationCanceled") == (
        "Failed to pair: AuthenticationCanceled"
    )
    assert bluetooth.failure("Pairing successful") is None


class FakeCtl:
    """Answers bluetoothctl calls from a table of (args prefix → (code, text)) and records them."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    async def __call__(self, *args, timeout=30):
        self.calls.append(args)
        for prefix, answer in self.answers:
            if args[: len(prefix)] == prefix:
                return answer
        return 0, ""


@pytest.fixture
def ctl(monkeypatch):
    def install(answers):
        fake = FakeCtl(answers)
        monkeypatch.setattr(bluetooth, "bluetoothctl", fake)
        return fake

    return install


async def test_status_marks_the_connected_ones(ctl):
    ctl([
        (("devices", "Paired"), (0, LISTING)),
        (("devices", "Connected"), (0, "Device 07:1A:FA:DE:72:75 BT Scanner HID_7275")),
    ])
    assert await bluetooth.status() == {
        "available": True,
        "paired": [
            {"mac": "07:1A:FA:DE:72:75", "name": "BT Scanner HID_7275", "connected": True},
            {"mac": "B8:B4:09:FA:86:D3", "name": "HART Right 85", "connected": False},
        ],
    }


async def test_status_without_bluetoothctl(ctl):
    ctl([(("devices", "Paired"), (None, "bluetoothctl is not installed"))])
    assert await bluetooth.status() == {"available": False, "paired": [], "note": "bluetoothctl is not installed"}


async def test_discover_puts_likely_scanners_first(ctl):
    fake = ctl([
        (("devices", "Paired"), (0, "Device B8:B4:09:FA:86:D3 HART Right 85")),
        (("devices",), (0, LISTING)),
    ])
    assert await bluetooth.discover("scan|barcode") == [
        {"mac": "07:1A:FA:DE:72:75", "name": "BT Scanner HID_7275", "paired": False, "scanner": True},
        {"mac": "B8:B4:09:FA:86:D3", "name": "HART Right 85", "paired": True, "scanner": False},
    ]
    assert fake.calls[0] == ("--timeout", str(bluetooth.SCAN_SECONDS), "scan", "on")


async def test_pair_drops_the_old_bond_first(ctl):
    fake = ctl([
        (("devices", "Paired"), (0, "Device 07:1A:FA:DE:72:75 BT Scanner HID_7275")),
        (("pair",), (0, "Pairing successful")),
    ])
    assert await bluetooth.pair("07:1A:FA:DE:72:75") == (True, "Paired. Scans should arrive now.")
    assert fake.calls[1:] == [
        ("remove", "07:1A:FA:DE:72:75"),
        ("pairable", "on"),
        ("pair", "07:1A:FA:DE:72:75"),
        ("trust", "07:1A:FA:DE:72:75"),
        ("connect", "07:1A:FA:DE:72:75"),
        ("pairable", "off"),
    ]


async def test_pair_reports_bluez_failures(ctl):
    ctl([
        (("devices", "Paired"), (0, "")),
        (("pair",), (1, "Attempting to pair with 07:1A:FA:DE:72:75\nFailed to pair: org.bluez.Error.AuthenticationCanceled")),
    ])
    fake = bluetooth.bluetoothctl
    assert await bluetooth.pair("07:1A:FA:DE:72:75") == (False, "Failed to pair: AuthenticationCanceled")
    assert fake.calls[-1] == ("pairable", "off")


async def test_addresses_are_checked():
    assert await bluetooth.pair("not a mac") == (False, "that is not a Bluetooth address")
    assert await bluetooth.forget("07:1A") == (False, "that is not a Bluetooth address")


async def test_forget(ctl):
    ctl([(("remove",), (0, "Device has been removed"))])
    assert await bluetooth.forget("07:1A:FA:DE:72:75") == (True, "Forgotten.")
