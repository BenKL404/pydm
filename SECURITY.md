# Security Policy

PyDM handles sensitive data: the browser extension forwards cookies to PyDM,
the session file stores them, and PyDM listens on a local Unix socket. Security
reports are taken seriously.

## Supported versions

Only the latest release and the `main` branch receive security fixes.

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately through
[GitHub private vulnerability reporting](https://github.com/BenKL404/pydm/security/advisories/new)
(repository → **Security** tab → **Report a vulnerability**).

Please include:

- what an attacker can do and under which conditions;
- steps to reproduce, or a proof of concept;
- your PyDM version or commit, distribution and browser.

You will get an answer within 7 days. Once the issue is confirmed, a fix is
prepared and released, and you are credited in the advisory unless you prefer
to stay anonymous.

## Scope

In scope, for example:

- another local user or a web page reaching the PyDM socket or the native host;
- cookies or session data leaking to the wrong site, to logs or to other users;
- a crafted URL, server response or file name writing outside the download folder;
- the extension exposing data or actions to web pages.

Out of scope: vulnerabilities in yt-dlp, ffmpeg, Python or the browser
themselves (report them upstream), and attacks that require an already
compromised user account.
