# Changelog

All notable changes to PyDM are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Already downloaded: adding a link PyDM has already taken now says so — with
  the date, and whether the file is still in place — and offers to download it
  again, open the existing file, or cancel, the way IDM does. The warning can
  be turned off from the dialog or from the preferences.
- Add dialog: when a site offers no thumbnail — most embedded players do not —
  the first frame of the stream is grabbed with ffmpeg and shown in its place.
  It is taken a couple of seconds in, since videos often open on black, and
  falls back to frame zero for very short streams.

### Changed

- The download badge shows up on its own as soon as a video is visible, without
  having to move the pointer over the player, and shrinks to its icon after a
  few seconds. Hovering it opens it again.
- Embedded players: a script running inside a frame cannot draw outside it, so
  the badge stayed inside the video on every site that embeds its player. The
  frame now describes its video to the page above it, which draws the badge
  over the frame — through nested frames too.
- The badge is now a rectangle rather than a pill, reads "Télécharger la
  vidéo", and sits flush against the video: just above its top-right corner, or
  inside that corner when the video touches the top of the window or lives in
  an embedded frame, where there is no room above it. Its shape is a setting:
  the full bar, a circle that expands on hover, or a circle alone.
- The extension popup was redesigned: no wrapped button labels, settings
  aligned on their first line with a hint below, and a status dot instead of a
  check mark.
- The toolbar's menu button now carries a gear rather than the sliders icon,
  which read as filters.

### Fixed

- Duplicate numbering piled up instead of carrying on: with `film.mp4` through
  `film (3).mp4` already there, three more downloads became `film (3) (1)` and
  `film (3) (2)`. Numbering now restarts from the root name — `film (4)`,
  `film (5)` — while a number that belongs to the title, such as
  `Matrix (2)` on a free name, is left alone.
- A finished download whose file was later moved or deleted came back as a
  fresh, paused task with an unknown size, because the session kept no trace of
  its progress. It now stays finished at 100 % and the status reads
  "Terminé · fichier déplacé".

## [1.8.3] - 2026-11-21

### Fixed

- Video size: for a fragmented stream, yt-dlp only knows bitrate × duration,
  which can be off by a factor of three. Once a few fragments are in, the size
  is extrapolated from what actually arrived, and the list shows "≈" as long as
  it remains an estimate. A size the server states exactly always wins.
- Video name: a direct stream (`master.m3u8`, `index.mp4`…) made yt-dlp title
  the video after the file name — "master". The page title is used instead for
  those links, while sites yt-dlp knows how to extract keep their own title.

## [1.8.2] - 2026-11-21

### Fixed

- Videos added together with the same title all aimed at the same file: three
  downloads could end up named `… (3).mp4`, overwriting each other. The name is
  now reserved under a lock, counting both the files already on disk — whatever
  their extension — and the videos running or queued in the same batch.
- Videos: yt-dlp wrote its fragments and `.part` files straight into the
  download folder, which became unusable for the whole download — hundreds of
  temporary files appearing and disappearing. They now go to a hidden
  `.pydm-temp` folder beside the destination, on the same disk, removed once
  nothing is left to resume.
- Videos: the progress and the announced size no longer jump back when yt-dlp
  moves from the video stream to the audio one. Both streams are now counted
  together, and the announced size never shrinks.

## [1.8.1] - 2026-11-21

### Changed

- The download badge now sits above the video aligned on its **right** edge
  rather than its left one, and is pushed back inside the window when the
  video is too narrow or too close to an edge.
- It reads "Télécharger la vidéo", the way IDM's panel does.

### Added

- Badge shape is now a setting, in the extension's popup: the full bar
  (default), a circle that expands on hover, or a circle alone. The change
  applies immediately, without reloading the page.

## [1.8.0] - 2026-11-20

### Changed

- The download badge no longer collapses into a small circle: it always shows
  "Télécharger avec PyDM" in full, and stays inside the window when the video
  sits against the right edge.

### Fixed

- Video names: players that serve `master.mp4`, `index.m3u8` or `playlist.mp4`
  produced downloads named after the stream instead of the video. The page
  title is now used whenever the link carries no meaningful name, both in the
  add dialog and for downloads added without confirmation.

## [1.7.1] - 2026-11-20

### Fixed

- Browser extension: the download badge was unreachable on players whose own
  controls — or Firefox's picture-in-picture button — sit in the same corner.
  Those are painted by the browser itself, above any z-index, so the badge now
  sits just above the video, outside it, the way IDM's panel does. When there
  is no room above, it falls back inside the video and picks a corner nothing
  covers, checked by hit test rather than guessed. It also stays visible while
  the pointer travels from the video to it.

## [1.7.0] - 2026-11-20

### Added

- Sessions that expire while a download waits: PyDM now keeps a permanent link
  to the browser extension and asks it for fresh headers when a server refuses
  a download it could serve before. Cookies captured when the link was added
  are no longer stale when the queue starts the download hours later. Asked
  once per start; if no browser is connected, nothing changes.
- Expiring links: PyDM now reads the deadline a signed link carries (AWS SigV4,
  CloudFront, Akamai tokens, JWT) and says "Ce lien a expiré, rechargez la page"
  instead of reporting an opaque 403. A planned download whose link is already
  dead is flagged in the queue.

### Changed

- Restrictive servers: a 403 or 429 is no longer treated as a network outage.
  The number of simultaneous connections allowed per host is halved on each
  refusal (with jitter and `Retry-After` honoured) and grows back as data
  flows; at one connection the remaining work is stitched back together and
  resumed one hole at a time, without re-downloading anything already written.
- The announced User-Agent now matches the platform PyDM runs on and stays
  pinned per host; the browser's own User-Agent, sent by the extension, still
  wins.

### Fixed

- Videos: a fragment the server would not serve was silently skipped, leaving a
  gap in the file. All fragments are now required.
- Range requests advertise `Accept-Encoding: identity`, and a compressed partial
  response stops the download instead of writing bytes at the wrong offsets.
- Browser extension: the "Télécharger avec PyDM" badge could end up out of
  reach — entirely off-screen on a player wider than the window, or straddling
  the edge of a narrow video, where moving towards it took the pointer out of
  the area that keeps it visible. It is now placed inside the *visible* part of
  the video, follows it while scrolling or resizing, is hidden when nothing of
  the video is left on screen, and never moves out from under the pointer.
- Browser extension: players that wrap their `<video>` in an open shadow root
  were invisible to the badge, which never appeared on those pages.

## [1.6.0] - 2026-11-20

### Added

- Per-download speed limit: right-click → "Limiter la vitesse", or the "Limite"
  row of the progress window; adjustable while downloading, kept in the
  session, shown with ⏱ in the Speed column and in the detail panel.
- Global speed limit from the status bar: click to turn it on or off, arrow to
  pick 256 KB/s to 10 MB/s or another value.
- Paste several links at once: pasting two or more links in the link field adds
  them right away; "Ajouter plusieurs liens…" (Ctrl+Shift+V) takes any text.

### Changed

- The status bar now reads "Vitesse illimitée" or "Limité à …" instead of always
  showing the configured value.

## [1.5.1] - 2026-11-10

### Fixed

- Release builds: the CI could not install Python 3.9 on the new Ubuntu 26.04
  runners, so 1.5.0 shipped without the AppImage and the Windows installer.
  1.5.1 has the same content as 1.5.0, with all downloads.

## [1.5.0] - 2026-11-10

### Changed

- New visual identity: toolbar actions are flat two-tone illustrations with one
  colour per action (green resume, amber pause, violet "start now" rocket, red
  bin, alarm-clock scheduler…), following the light or dark theme.
- Empty list, empty filter and empty search now show an illustration with a
  short explanation; the welcome message and the add window (link error, DRM)
  use illustrations too.

### Fixed

- Very long titles or links without spaces no longer widen the main, add and
  progress windows beyond the screen; the add window shows the title on two
  lines with the full title as a tooltip.

## [1.4.0] - 2026-10-22

### Added

- Experimental Windows build: `PyDM-<version>-Setup.exe` (per-user, no
  administrator rights) and a portable zip. PyDM registers itself with the
  browsers in the user's registry on launch (moving the folder is repaired on
  the next launch), "Start with the session" uses the `Run` key, and the
  uninstaller removes everything. The browser talks to PyDM through a per-user
  named pipe. Built and tested end to end on a Windows CI machine.
- `pydm --remove-integration` removes the browser link, menu entry and
  autostart (Windows uninstaller, or by hand).

### Changed

- File names are made valid on Windows (forbidden characters, reserved names,
  trailing dots); Linux behaviour is unchanged.
- Typed folders are normalised (`~` expanded, one kind of separator).
- On Windows, "power off" and "suspend" at the end of the queue use
  `shutdown` and `SetSuspendState`; a clear message explains that Chrome's
  cookies cannot be read on Windows.

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

[Unreleased]: https://github.com/BenKL404/pydm/compare/v1.8.3...HEAD
[1.8.3]: https://github.com/BenKL404/pydm/compare/v1.8.2...v1.8.3
[1.8.2]: https://github.com/BenKL404/pydm/compare/v1.8.1...v1.8.2
[1.8.1]: https://github.com/BenKL404/pydm/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/BenKL404/pydm/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/BenKL404/pydm/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/BenKL404/pydm/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/BenKL404/pydm/compare/v1.5.1...v1.6.0
[1.5.1]: https://github.com/BenKL404/pydm/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/BenKL404/pydm/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/BenKL404/pydm/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/BenKL404/pydm/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/BenKL404/pydm/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/BenKL404/pydm/releases/tag/v1.1.0
[1.0.0]: https://github.com/BenKL404/pydm/commit/fac5bdb
