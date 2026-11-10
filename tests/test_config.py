import json

from qrs_kiosk.config import Config


def make(tmp_path, toml=""):
    cfg_path = tmp_path / "qrs-kiosk.toml"
    cfg_path.write_text(toml)
    c = Config(cfg_path, tmp_path / "state")
    c.load()
    return c


def test_defaults_provisioning_and_state_layer(tmp_path):
    c = make(tmp_path, '[qrs]\nbase = "http://localhost:4001/"\n[kiosk]\nidle_seconds = 60\n')
    assert c.base == "http://localhost:4001"
    assert c.idle_seconds == 60
    assert c.port == 4010
    c.set("kiosk", "idle_seconds", 10)
    assert c.idle_seconds == 10
    again = Config(c.config_path, c.state_dir)
    again.load()
    assert again.idle_seconds == 10
    assert again.settings()["kiosk"]["idle_seconds"] == 10
    assert json.loads(c.state_path.read_text())["settings"]["kiosk"]["idle_seconds"] == 10


def test_overrides_win(tmp_path):
    c = make(tmp_path)
    c.override("kiosk", "port", 5000)
    assert c.port == 5000


def test_the_plate_is_kept(tmp_path):
    c = make(tmp_path)
    assert c.plate is None
    c.plate = {"url": "u", "label": "Dock"}
    again = Config(c.config_path, c.state_dir)
    again.load()
    assert again.plate == {"url": "u", "label": "Dock"}
    again.plate = None
    assert Config(c.config_path, c.state_dir).plate is None


def test_a_missing_or_broken_file_means_defaults(tmp_path):
    c = Config(tmp_path / "none.toml", tmp_path / "state")
    c.load()
    assert c.base == "https://app.qrsensor.com"
    c = make(tmp_path, "not = [toml")
    assert c.base == "https://app.qrsensor.com"
