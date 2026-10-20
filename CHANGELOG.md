# Changelog

All notable changes to PyDM are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/BenKL404/pydm/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/BenKL404/pydm/releases/tag/v1.0.0
