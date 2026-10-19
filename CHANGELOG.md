# Changelog

All notable changes to PyDM are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- The menu entry in `pydm.desktop` now runs the `pydm` command.

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
