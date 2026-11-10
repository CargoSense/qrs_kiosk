"""
Over-the-air updates of the daemon itself. A release on GitHub carries a
wheel and a SHA256SUMS file. The updater installs a new version into its own
virtualenv under `<root>/versions/<version>`, checks it starts, points
`<root>/current` at it (keeping `<root>/previous`), and exits so systemd
starts the new one. `bin/qrs-kiosk-run` moves `current` back to `previous`
when a version fails to come up healthy three times running.

Only the daemon updates this way: the OS and the browser come with the
image. Downloads are small, which matters over HaLow.
"""

import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import aiohttp

from qrs_kiosk import __version__

log = logging.getLogger(__name__)

API = "https://api.github.com"


def parse_version(text):
    parts = re.findall(r"\d+", str(text or ""))
    return tuple(int(p) for p in parts) if parts else (0,)


def newer(candidate, current):
    return parse_version(candidate) > parse_version(current)


def checksum_of(sums_text, filename):
    """The hash SHA256SUMS lists for `filename`, or None."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Updater:
    def __init__(self, config, http, state_dir):
        self.config = config
        self.http = http
        self.state_dir = Path(state_dir)
        self.status = {"current": __version__, "available": None, "state": "idle", "error": None, "checked_at": None}
        self.lock = asyncio.Lock()

    @property
    def root(self):
        return Path(self.config.get("update", "root"))

    def headers(self, accept="application/vnd.github+json"):
        h = {"accept": accept, "user-agent": f"qrs-kiosk/{__version__}"}
        token = self.config.get("update", "token")
        if token:
            h["authorization"] = f"Bearer {token}"
        return h

    async def check(self):
        """Asks GitHub for the latest release; records it in `status` when newer."""
        repo = self.config.get("update", "repo")
        if not repo:
            return None
        self.status["state"] = "checking"
        try:
            async with self.http.get(
                f"{API}/repos/{repo}/releases/latest", headers=self.headers(), timeout=aiohttp.ClientTimeout(total=30)
            ) as res:
                if res.status != 200:
                    raise RuntimeError(f"GitHub answered {res.status}")
                release = await res.json()
        except (aiohttp.ClientError, RuntimeError, TimeoutError, ValueError) as e:
            self.status.update(state="idle", error=f"check failed: {e}")
            log.warning("update check failed: %s", e)
            return None
        self.status.update(state="idle", error=None, checked_at=time.time())
        version = release.get("tag_name", "")
        assets = {a["name"]: a for a in release.get("assets", [])}
        wheel = next((a for n, a in assets.items() if n.endswith(".whl")), None)
        if not wheel or not newer(version, __version__):
            self.status["available"] = None
            return None
        self.status["available"] = {
            "version": version.lstrip("v"),
            "wheel": wheel["name"],
            "wheel_url": wheel["url"],
            "sums_url": assets["SHA256SUMS"]["url"] if "SHA256SUMS" in assets else None,
        }
        log.info("update available: %s", version)
        return self.status["available"]

    async def download(self, url, dest):
        async with self.http.get(
            url, headers=self.headers("application/octet-stream"), timeout=aiohttp.ClientTimeout(total=1800)
        ) as res:
            if res.status != 200:
                raise RuntimeError(f"download of {url} answered {res.status}")
            with open(dest, "wb") as f:
                async for chunk in res.content.iter_chunked(1 << 16):
                    f.write(chunk)

    async def apply(self):
        """Installs the available release. Returns True when the daemon should exit for restart."""
        async with self.lock:
            available = self.status.get("available")
            if not available:
                return False
            version = available["version"]
            self.status.update(state="downloading", error=None)
            try:
                await self._install(available)
            except Exception as e:  # noqa: BLE001  (every failure is reported the same way)
                self.status.update(state="idle", error=f"update to {version} failed: {e}")
                log.exception("update to %s failed", version)
                return False
            self.status.update(state="restarting", error=None)
            log.info("updated to %s; restarting", version)
            return True

    async def _install(self, available):
        version = available["version"]
        versions = self.root / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            wheel = Path(tmp) / available["wheel"]
            await self.download(available["wheel_url"], wheel)
            if available.get("sums_url"):
                sums = Path(tmp) / "SHA256SUMS"
                await self.download(available["sums_url"], sums)
                want = checksum_of(sums.read_text(), available["wheel"])
                if not want:
                    raise RuntimeError("SHA256SUMS does not list the wheel")
                if sha256(wheel) != want:
                    raise RuntimeError("the wheel's checksum does not match SHA256SUMS")
            self.status["state"] = "installing"
            target = versions / version
            if target.exists():
                shutil.rmtree(target)
            uv = shutil.which("uv") or str(self.root / "bin" / "uv")
            await self.sh(uv, "venv", "--quiet", str(target))
            await self.sh(uv, "pip", "install", "--quiet", "--python", str(target / "bin" / "python"), f"qrs-kiosk[pi] @ {wheel.as_uri()}")
            await self.sh(
                str(target / "bin" / "qrs-kiosk"), "--check",
                "--config", str(self.config.config_path), "--state", str(self.state_dir),
            )
        current = self.root / "current"
        previous = self.root / "previous"
        if current.is_symlink():
            relink(previous, os.readlink(current))
        relink(current, str(target))
        for stale in (self.state_dir / "starts",):
            stale.unlink(missing_ok=True)

    async def sh(self, *args):
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), 1800)
        if proc.returncode != 0:
            raise RuntimeError(f"{args[0]} failed ({proc.returncode}): {out.decode(errors='replace')[-2000:]}")

    def mark_healthy(self):
        """This version came up and stayed up: never roll back to before it."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / f"healthy-{__version__}").touch()
        (self.state_dir / "starts").unlink(missing_ok=True)


def relink(link, target):
    tmp = link.with_name(link.name + ".new")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)
