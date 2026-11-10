from qrs_kiosk.updater import checksum_of, newer, parse_version


def test_versions():
    assert parse_version("v1.2.10") == (1, 2, 10)
    assert newer("v0.2.0", "0.1.9")
    assert not newer("v0.1.0", "0.1.0")
    assert not newer("", "0.1.0")


def test_sha256sums_lines():
    text = "abc  qrs_kiosk-0.2.0-py3-none-any.whl\ndef *SHA256SUMS\n"
    assert checksum_of(text, "qrs_kiosk-0.2.0-py3-none-any.whl") == "abc"
    assert checksum_of(text, "SHA256SUMS") == "def"
    assert checksum_of(text, "other.whl") is None
