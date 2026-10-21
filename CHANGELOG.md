# Changelog

All notable changes to PyDM are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.3.0] - 2026-10-21

### Added

- One-file install: `PyDM-<version>-x86_64.AppImage` bundles Python, Qt, yt-dlp
  and ffmpeg. On launch it adds itself to the applications menu and registers
  with the browsers (moving the file is repaired on the next launch); a welcome
  message links to the extension. "Remove PyDM from the system" in Preferences
  undoes it.
- `pydm --native-host`: the same program serves as the browser's native host.

### Changed

- "Start PyDM with the session" starts the AppImage when PyDM runs from one.

## [1.2.0] - 2026-10-21

### Changed

- Video button in the browser: a discreet round button with the PyDM logo that
  expands to "Télécharger avec PyDM" on hover, with sending, success and error
  states (extension 1.1.0).
- HTTP 403 refusals now explain the likely cause (link tied to the browser or
  its IP address, VPN or proxy, or expired link).

### Fixed

- "Resume" is no longer shown as possible on a task in error.
- Video button missing on sites whose page is transformed or wider than the
  window (extension 1.1.1).

## [1.1.0] - 2026-10-20

### Added

- Add window before each download: thumbnail, title, duration, size, the real
  list of available video qualities with their sizes, editable name and
  folder; Download, Later (added paused) or Cancel. Several links at once open
  a single checklist window. "Don't ask again" option, also in Preferences.

- New Qt 6 interface: dense table with real progress bars, sortable columns,
  search, detail panel, status bar with total speed and a speed graph.
- PyDM logo and a set of icons drawn for PyDM; light and dark themes that
  follow the system.
- System tray icon: closing the window keeps PyDM running; notifications when a
  download finishes or fails.
- Right-click menu, keyboard shortcuts, drag-and-drop and pasting of several
  links at once, deleting a downloaded file from the list.
- Preferences window: download folder, connections, theme, clipboard,
  notifications, close to tray, start with the session (`pydm --minimized`).
- Settings are saved (`~/.config/pydm/settings.json`).
- Test suite (`python3 -m unittest discover -s tests -t .`).

### Changed

- `install.sh` installs PyDM in a private Python environment with PySide6 and
  yt-dlp; running it again updates them.
- The code is now a `pydm/` package; run it with `python3 -m pydm`.
- An unreadable settings or session file is kept as `.bak` instead of being lost.

### Removed

- The Tkinter interface.

- Progress window for each download (opens when it starts, can be turned off):
  speed, time left, map of the connections at their real position in the file,
  per-connection table, pause/resume, cancel, "close when done".
- Videos are analysed as soon as their page opens (extension option, PyDM must be
  running) and analyses are kept 10 minutes, so the add window opens with the
  quality list ready; the tab title and the YouTube thumbnail show immediately.
- Sidebar with live counts to filter the list by state and by file type
  (combined with search); right-click a type to open its folder; Ctrl+B to hide it.
- Download queue: limit of simultaneous downloads, "Later" scheduled queue with a
  daily time window or manual start, "Force", reordering (Ctrl+↑/↓), global speed
  limit toggled from the status bar, and an end-of-queue action (quit, suspend,
  power off) with a 60 s countdown.
- Files are sorted into sub-folders by type (videos, music, documents, images,
  archives, programs), configurable in Preferences; new "image" file type.

### Fixed

- YouTube videos failing with "The page needs to be reloaded": videos are now
  tried without cookies first, then with the browser's cookies only if needed.

- The menu entry in `pydm.desktop` now runs the `pydm` command and uses the PyDM icon.

## [1.0.0] - 2026-10-19

First public version.

### Added

- Multi-connection downloads with dynamic segment splitting.
- Pause and resume, kept across restarts, with automatic retries.
- Streaming video downloads through yt-dlp, with quality selection and MP3 extraction.
- Graphical interface (Tkinter) and command line.
- Clipboard monitoring.
- Browser extension for Firefox and Chromium-based browsers: download
  interception, video button, context menu, cookie and referrer forwarding.
- Native messaging host and per-user installer.

[Unreleased]: https://github.com/BenKL404/pydm/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/BenKL404/pydm/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/BenKL404/pydm/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/BenKL404/pydm/releases/tag/v1.1.0
[1.0.0]: https://github.com/BenKL404/pydm/commit/fac5bdb
