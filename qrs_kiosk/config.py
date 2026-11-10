"""
Two files make the configuration. The provisioning file is TOML on the boot
partition, written before the device ships (or edited from a laptop with the
SD card). The state file is JSON in the state directory, written by the
daemon: the wall plate, and any setting changed from the settings page. State
wins over provisioning, which wins over the defaults here.
"""

import copy
import json
import logging
import tomllib
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {
    "qrs": {"base": "https://app.qrsensor.com"},
    "kiosk": {"port": 4010, "idle_seconds": 300, "pin": "", "name": ""},
    "scanner": {
        "match": "scan|barcode|symbol|honeywell|zebra|datalogic|newland|socket|inateck|tera|netum",
        "terminator": "KEY_ENTER",
        "gap_ms": 150,
    },
    "wifi": {"ssid": "", "password": "", "hidden": False},
    "update": {"repo": "CargoSense/qrs_kiosk", "every_minutes": 60, "token": "", "root": "/opt/qrs-kiosk"},
}


class Config:
    def __init__(self, config_path: Path, state_dir: Path):
        self.config_path = config_path
        self.state_dir = state_dir
        self.state_path = state_dir / "state.json"
        self.provisioned = {}
        self.state = {}
        self.overrides = {}

    def load(self):
        self.provisioned = self._read_toml()
        self.state = self._read_state()

    def _read_toml(self):
        try:
            with open(self.config_path, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            log.warning("no provisioning file at %s; using defaults", self.config_path)
            return {}
        except tomllib.TOMLDecodeError as e:
            log.error("provisioning file %s is not valid TOML: %s", self.config_path, e)
            return {}

    def _read_state(self):
        try:
            return json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            log.error("state file %s unreadable: %s", self.state_path, e)
            return {}

    def _write_state(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        tmp.replace(self.state_path)

    def get(self, section, key):
        for layer in (self.overrides, self.state.get("settings", {}), self.provisioned):
            if key in layer.get(section, {}):
                return layer[section][key]
        return DEFAULTS[section][key]

    def set(self, section, key, value):
        """A setting changed at runtime: kept in state, over the provisioning file."""
        self.state.setdefault("settings", {}).setdefault(section, {})[key] = value
        self._write_state()

    def override(self, section, key, value):
        self.overrides.setdefault(section, {})[key] = value

    def settings(self):
        """Every setting as it stands, by section."""
        out = copy.deepcopy(DEFAULTS)
        for section in out:
            for key in out[section]:
                out[section][key] = self.get(section, key)
        return out

    @property
    def base(self):
        return str(self.get("qrs", "base")).rstrip("/")

    @property
    def port(self):
        return int(self.get("kiosk", "port"))

    @property
    def idle_seconds(self):
        return int(self.get("kiosk", "idle_seconds"))

    @property
    def pin(self):
        return str(self.get("kiosk", "pin"))

    @property
    def plate(self):
        """The wall plate: {"url", "label"} or None."""
        return self.state.get("plate")

    @plate.setter
    def plate(self, value):
        if value is None:
            self.state.pop("plate", None)
        else:
            self.state["plate"] = value
        self._write_state()
