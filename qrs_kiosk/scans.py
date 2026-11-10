"""
What a USB scanner types, turned back into what it read. The scanner is a
keyboard: one key event per character, Enter (or a configured terminator) at
the end. Pure, so it runs on a laptop with no scanner.

A scanner set to send AIM symbology identifiers prefixes each read with
`]` + a code letter + a modifier digit (`]Q3` for a QR code). The shell's
`lengths` rule keys on the symbology, so the prefix is worth turning on.

A payload with newlines in it (several serials in one QR code) only
survives if the scanner sends control characters as Ctrl+letter rather than
as Enter, and ends the read with a different key: see the README.
"""

from dataclasses import dataclass

AIM = {
    "Q": "qr",
    "d": "datamatrix",
    "C": "code128",
    "A": "code39",
    "G": "code93",
    "F": "codabar",
    "I": "i2of5",
    "L": "pdf417",
    "z": "aztec",
}

EAN_BY_LENGTH = {13: "ean13", 12: "upca", 8: "ean8", 6: "upce"}

KEYS = {
    "KEY_1": ("1", "!"), "KEY_2": ("2", "@"), "KEY_3": ("3", "#"), "KEY_4": ("4", "$"), "KEY_5": ("5", "%"),
    "KEY_6": ("6", "^"), "KEY_7": ("7", "&"), "KEY_8": ("8", "*"), "KEY_9": ("9", "("), "KEY_0": ("0", ")"),
    "KEY_MINUS": ("-", "_"), "KEY_EQUAL": ("=", "+"), "KEY_LEFTBRACE": ("[", "{"), "KEY_RIGHTBRACE": ("]", "}"),
    "KEY_SEMICOLON": (";", ":"), "KEY_APOSTROPHE": ("'", '"'), "KEY_GRAVE": ("`", "~"), "KEY_BACKSLASH": ("\\", "|"),
    "KEY_COMMA": (",", "<"), "KEY_DOT": (".", ">"), "KEY_SLASH": ("/", "?"), "KEY_SPACE": (" ", " "),
    "KEY_TAB": ("\t", "\t"),
    "KEY_KP0": ("0", "0"), "KEY_KP1": ("1", "1"), "KEY_KP2": ("2", "2"), "KEY_KP3": ("3", "3"), "KEY_KP4": ("4", "4"),
    "KEY_KP5": ("5", "5"), "KEY_KP6": ("6", "6"), "KEY_KP7": ("7", "7"), "KEY_KP8": ("8", "8"), "KEY_KP9": ("9", "9"),
    "KEY_KPDOT": (".", "."), "KEY_KPMINUS": ("-", "-"), "KEY_KPPLUS": ("+", "+"), "KEY_KPSLASH": ("/", "/"),
    "KEY_KPASTERISK": ("*", "*"),
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[f"KEY_{_c.upper()}"] = (_c, _c.upper())

SHIFT = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}
CTRL = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL"}
CONTROL_CHARS = {"KEY_J": "\n", "KEY_M": "\r", "KEY_I": "\t"}


@dataclass(frozen=True)
class Scan:
    payload: str
    symbology: str | None = None


def split_aim(text):
    """The payload and symbology from a read that may carry an AIM prefix."""
    if len(text) >= 3 and text[0] == "]":
        code, body = text[1], text[3:]
        if code == "E":
            return body, EAN_BY_LENGTH.get(len(body))
        if code in AIM:
            return body, AIM[code]
        if code == "X":
            return body, None
    return text, None


class Decoder:
    """
    Feeds on key events (`feed`) and yields a Scan when the terminator
    arrives. `flush` yields whatever is buffered: for a scanner that ends a
    read with nothing, the reader calls it after a pause.
    """

    def __init__(self, terminator="KEY_ENTER"):
        self.terminators = {terminator, "KEY_KPENTER"} if terminator == "KEY_ENTER" else {terminator}
        self.buffer = []
        self.shift = False
        self.ctrl = False

    def feed(self, key, pressed):
        if key in SHIFT:
            self.shift = pressed
            return None
        if key in CTRL:
            self.ctrl = pressed
            return None
        if not pressed:
            return None
        if key in self.terminators:
            return self.flush()
        if self.ctrl:
            if key in CONTROL_CHARS:
                self.buffer.append(CONTROL_CHARS[key])
            return None
        pair = KEYS.get(key)
        if pair:
            self.buffer.append(pair[1] if self.shift else pair[0])
        return None

    def flush(self):
        if not self.buffer:
            return None
        text = "".join(self.buffer)
        self.buffer = []
        payload, symbology = split_aim(text)
        return Scan(payload, symbology) if payload else None
