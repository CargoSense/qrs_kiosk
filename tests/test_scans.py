from qrs_kiosk.scans import Decoder, Scan, split_aim


def type_keys(decoder, text, terminator="KEY_ENTER"):
    """Presses the keys a scanner would for `text`, then the terminator."""
    out = []
    for c in text:
        key, shifted = key_for(c)
        if shifted:
            decoder.feed("KEY_LEFTSHIFT", True)
        out.append(decoder.feed(key, True))
        decoder.feed(key, False)
        if shifted:
            decoder.feed("KEY_LEFTSHIFT", False)
    out.append(decoder.feed(terminator, True))
    decoder.feed(terminator, False)
    return [s for s in out if s]


def key_for(c):
    from qrs_kiosk.scans import KEYS

    for key, (plain, shifted) in KEYS.items():
        if key.startswith("KEY_KP"):
            continue
        if c == plain:
            return key, False
        if c == shifted:
            return key, True
    raise ValueError(c)


def test_a_sticker_url_comes_back_whole():
    url = "https://app.qrsensor.com/s/0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0/1k2j3h4g"
    assert type_keys(Decoder(), url) == [Scan(url)]


def test_shifted_characters_and_symbols():
    assert type_keys(Decoder(), "Ab-C_1!?") == [Scan("Ab-C_1!?")]


def test_an_aim_prefix_names_the_symbology():
    assert type_keys(Decoder(), "]Q3hello") == [Scan("hello", "qr")]
    assert type_keys(Decoder(), "]C0ABC123") == [Scan("ABC123", "code128")]
    assert type_keys(Decoder(), "]E01234567890123") == [Scan("1234567890123", "ean13")]
    assert type_keys(Decoder(), "]X0raw") == [Scan("raw", None)]


def test_a_bracket_that_is_not_a_prefix_stays():
    assert split_aim("]") == ("]", None)
    assert split_aim("]]3x") == ("]]3x", None)
    assert split_aim("[Q3x") == ("[Q3x", None)


def test_control_characters_as_ctrl_combinations():
    d = Decoder(terminator="KEY_TAB")
    d.feed("KEY_A", True)
    d.feed("KEY_A", False)
    d.feed("KEY_LEFTCTRL", True)
    d.feed("KEY_J", True)
    d.feed("KEY_J", False)
    d.feed("KEY_LEFTCTRL", False)
    d.feed("KEY_B", True)
    d.feed("KEY_B", False)
    assert d.feed("KEY_TAB", True) == Scan("a\nb")


def test_keypad_enter_also_ends_a_read():
    d = Decoder()
    d.feed("KEY_1", True)
    assert d.feed("KEY_KPENTER", True) == Scan("1")


def test_flush_after_a_pause_and_empty_reads():
    d = Decoder()
    assert d.flush() is None
    assert d.feed("KEY_ENTER", True) is None
    d.feed("KEY_X", True)
    assert d.flush() == Scan("x")
    assert d.flush() is None


def test_unknown_keys_are_skipped():
    d = Decoder()
    d.feed("KEY_F12", True)
    d.feed("KEY_Z", True)
    assert d.flush() == Scan("z")
