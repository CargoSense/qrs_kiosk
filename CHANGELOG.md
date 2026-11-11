# Changelog

Each release is a tag `v<version>` on this repository; terminals install
the newest release themselves. Entries say what a terminal's operator or
installer would notice.

## Unreleased

- A code scanned while no scan overlay is open goes to the shell anyway.
  A screen with one button that leads to a scan has that button pressed
  and the code handed to the scan it opens, so the operator scans a tag
  without first tapping "Scan tag". The note "Not a code this terminal
  knows" now comes from the page, after the shell has had no use for it,
  and also when the frame shows no shell.

## 0.1.1 (2026-11-11)

- A PIN is 4 to 8 digits. The settings page accepted any text, and a PIN
  the digit pad cannot enter locked it.
- The network and update checks run as soon as the daemon starts, not
  after the first interval of uptime.

## 0.1.0 (2026-11-11)

First release.

- A daemon that reads the barcode scanner, decides what each scan means
  (a sticker, the wall plate, a WiFi code, a terminal command), serves
  the terminal page and the PIN-gated settings page, joins WiFi, and
  updates itself from GitHub Releases with rollback.
- The terminal page: a sidebar with Start, the place and applet, a
  clock and the status, beside the QRS shell in a frame.
- An installer for Raspberry Pi OS: a kiosk user whose labwc session
  starts the on-screen keyboard and Chromium as a maximized window on
  the rotated touchscreen, with the daemon under systemd.
