"""updater.py – Check for application updates via the GitHub Releases API.

Uses only the Python standard library (``urllib.request``) – no third-party
dependencies.  All network access happens here; callers are responsible for
running :func:`check_for_update` on a background thread and marshalling the
result back to the UI thread (Tk is not thread-safe).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENT_VERSION = "1.2"
REPO = "NEBULON001/App-launcher"

_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT = 8  # seconds
_USER_AGENT = "AppLauncher/" + CURRENT_VERSION


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class UpdateInfo:
    """Metadata describing an available update."""

    latest_version: str   # e.g. "1.1" (leading 'v' stripped)
    download_url: str     # release html_url or first asset's browser_download_url
    release_notes: str    # release body (may be empty)


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

def _normalize_version(version: str) -> tuple[int, ...]:
    """Strip a leading ``v``/``V`` and convert ``"1.10.0"`` → ``(1, 10, 0)``.

    Non-numeric segments are treated as ``0`` so malformed values never raise.
    """
    v = version.strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    parts: list[int] = []
    for segment in v.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings.

    Returns:
        1  if *v1* > *v2*
        0  if *v1* == *v2*
       -1  if *v1* < *v2*

    Leading ``v``/``V`` is stripped, segments are compared numerically, and
    the shorter tuple is zero-padded so that ``1.0`` == ``1.0.0``.
    """
    t1 = _normalize_version(v1)
    t2 = _normalize_version(v2)
    length = max(len(t1), len(t2))
    t1 = t1 + (0,) * (length - len(t1))
    t2 = t2 + (0,) * (length - len(t2))
    if t1 > t2:
        return 1
    if t1 < t2:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Update check
# ---------------------------------------------------------------------------

def check_for_update() -> UpdateInfo | None:
    """Query GitHub for the latest release.

    Returns:
        An :class:`UpdateInfo` when a version newer than
        :data:`CURRENT_VERSION` is available, otherwise ``None``.

    Never raises: network errors, timeouts, HTTP 403 (API rate limit),
    parse errors and missing fields all collapse to ``None``.
    """
    # --- Network request (any failure → None) ---
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        # urlopen raises HTTPError for 4xx/5xx (covers 403 rate limit).
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        # 403 API rate limit / other HTTP error status.
        return None
    except (urllib.error.URLError, OSError, TimeoutError):
        # DNS / connection / timeout / socket errors.
        return None
    except Exception:
        # Any other low-level failure – never raise out of this function.
        return None

    # --- JSON parsing (any failure → None) ---
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    tag_name = data.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        return None

    latest_version = tag_name[1:] if tag_name[:1] in ("v", "V") else tag_name

    # Only report when strictly newer than the current version.
    if compare_versions(latest_version, CURRENT_VERSION) <= 0:
        return None

    # Download URL: prefer the first asset's browser_download_url,
    # fall back to the release's html_url.
    download_url = ""
    assets = data.get("assets")
    if isinstance(assets, list) and assets:
        first = assets[0]
        if isinstance(first, dict):
            url = first.get("browser_download_url")
            if isinstance(url, str) and url:
                download_url = url
    if not download_url:
        html_url = data.get("html_url")
        if isinstance(html_url, str) and html_url:
            download_url = html_url
    if not download_url:
        return None

    release_notes = data.get("body")
    if not isinstance(release_notes, str):
        release_notes = ""

    return UpdateInfo(
        latest_version=latest_version,
        download_url=download_url,
        release_notes=release_notes,
    )
