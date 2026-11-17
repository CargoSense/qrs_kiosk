# Changelog

Each release is a tag `v<version>` on this repository; terminals install
the newest release themselves. Entries say what a terminal's operator or
installer would notice.

## Unreleased

## 0.1.2 (2026-11-17)

- The settings page pairs a Bluetooth scanner: put the scanner in pairing
  mode, tap "Find scanners", tap the scanner. A scanner that has lost the
  terminal is paired again the same way. Paired scanners are listed there
  with a Forget button.
- A code scanned while no scan overlay is open goes to the shell anyway.
  A screen with one button that leads to a scan has that button pressed
  and the code handed to the scan it opens, so the operator scans a tag
  without first tapping "Scan tag". The note "Not a code this terminal
  knows" now comes from the page, after the shell has had no use for it,
  and also when the frame shows no shell.
- When the QRS server cannot be reached, the frame says "We're currently
  offline" instead of showing the browser's error page. The daemon checks
  the server every 30 seconds, every 5 while it is down, and the page loads
  the shell again when it is back.
- The browser caches none of the terminal's pages, scripts or styles, so
  an update's new settings page is not left running the old script.

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
