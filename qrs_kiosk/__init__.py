from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qrs-kiosk")
except PackageNotFoundError:
    __version__ = "0.0.0"
