import argparse
import asyncio
import logging
import sys
from pathlib import Path

from qrs_kiosk import __version__
from qrs_kiosk.config import Config

DEFAULT_CONFIG = "/boot/firmware/qrs-kiosk.toml"
DEFAULT_STATE = "/var/lib/qrs-kiosk"


def parse(argv):
    p = argparse.ArgumentParser(prog="qrs-kiosk", description="The QR Sensor terminal daemon.")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="the provisioning file (TOML)")
    p.add_argument("--state", default=DEFAULT_STATE, help="where runtime state is kept")
    p.add_argument("--port", type=int, help="override the port the page is served on")
    p.add_argument("--dev", action="store_true", help="also take scans from POST /dev/scan")
    p.add_argument("--check", action="store_true", help="load the config and exit: the updater's health check")
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config(Path(args.config), Path(args.state))
    config.load()
    if args.port:
        config.override("kiosk", "port", args.port)
    if args.check:
        import qrs_kiosk.app  # noqa: F401  (imports everything the daemon needs)

        print(f"qrs-kiosk {__version__} ok: base {config.base}, port {config.port}")
        return 0

    from qrs_kiosk.app import run

    try:
        asyncio.run(run(config, dev=args.dev))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
