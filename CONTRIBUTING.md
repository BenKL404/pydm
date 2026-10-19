# Contributing to PyDM

Thanks for your interest in PyDM! Bug reports, ideas, documentation fixes and
code are all welcome. Contributions in English or French are fine.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting a bug or suggesting a feature

Open an [issue](https://github.com/BenKL404/pydm/issues/new/choose) using the
matching template. For a bug, please include your distribution, Python version,
browser, yt-dlp version (`yt-dlp --version`) and, when possible, the URL that
fails.

Security issues must **not** be reported in public issues: see [SECURITY.md](SECURITY.md).

## Project layout

| Path | Role |
|---|---|
| `pydm/` | Python package: `engine.py` (downloads), `ipc.py` (local socket), `cli.py` (command line), `tkgui.py` (current interface) |
| `pydm_host.py` | Native messaging host between the browser and PyDM |
| `extension/` | Browser extension (Manifest V3, Chrome and Firefox) |
| `pydm-extension.zip` | Packaged extension for Firefox, built from `extension/` |
| `install.sh` | Per-user installer and native host registration |
| `docs/specs/` | Design documents for upcoming features |

## Development setup

```bash
git clone https://github.com/BenKL404/pydm.git
cd pydm
python3 -m pydm                  # run the GUI straight from the repository
python3 -m pydm URL -n 4         # or the command line
```

To test the browser integration, run `./install.sh` and load `extension/` as an
unpacked extension (see the [README](README.md#browser-extension)).
`install.sh` copies the Python files, so run it again after changing them.

## Rules for code changes

- **Standard library only.** PyDM must keep working with nothing but Python and
  Tkinter. yt-dlp and ffmpeg stay optional and are detected at runtime.
- **Keep the user-facing text in French** (interface, messages, `LISEZMOI.md`).
  Code identifiers are in English, and code comments follow the existing style.
- **Keep the shared identifiers in sync.** The native host name
  `com.pydm.host`, the Chrome extension ID (derived from the `key` in
  `extension/manifest.json`) and the Firefox ID `pydm@local` appear in both
  `install.sh` and the extension. The socket path is defined in both
  `pydm/ipc.py` and `pydm_host.py`.
- **Rebuild the Firefox package** after any change in `extension/`:

  ```bash
  rm -f pydm-extension.zip && (cd extension && zip -r ../pydm-extension.zip .)
  ```

  CI fails if the zip does not match the folder.

## Checks

Run the same checks as CI before opening a pull request:

```bash
python3 -m compileall -q pydm pydm_host.py
sh -n install.sh
node --check extension/*.js
python3 -m unittest discover -s tests -t .
```

New features and bug fixes should come with tests in `tests/` (standard
`unittest`, no extra dependency) whenever the code can be tested without the GUI.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Keep each pull request focused on one change.
3. Write clear commit messages: a short summary line, then the why if needed.
4. Add an entry under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. Update `README.md` and `LISEZMOI.md` when behavior visible to users changes.
6. Fill in the pull request template.

## License

By contributing, you agree that your contributions are licensed under the
[GNU General Public License v3.0 or later](LICENSE), like the rest of the project.
