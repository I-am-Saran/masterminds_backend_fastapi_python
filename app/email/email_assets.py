"""Inline email assets (CID-embedded images)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

INLINE_LOGO_CID = "masterminds_logo"
INLINE_LOGO_FILENAME = "master-minds-logo.png"
_LOGO_PATH = Path(__file__).resolve().parent / "assets" / INLINE_LOGO_FILENAME


def logo_asset_path() -> Path:
    return _LOGO_PATH


def load_logo_bytes() -> Optional[bytes]:
    if not _LOGO_PATH.is_file():
        logger.warning("Email inline logo asset not found: %s", _LOGO_PATH)
        return None
    return _LOGO_PATH.read_bytes()


def html_uses_inline_logo(html: str) -> bool:
    if not html:
        return False
    needle = f"cid:{INLINE_LOGO_CID}"
    return needle in html.lower()


def normalize_html_logo_references(html: str) -> str:
    """Rewrite legacy external logo URLs to CID for stored templates."""
    if not html:
        return html
    import re

    html = re.sub(
        r'src="\{\{\s*logo_url\s*\}\}"',
        f'src="cid:{INLINE_LOGO_CID}"',
        html,
        flags=re.I,
    )
    html = re.sub(
        r'src="[^"]*master-minds-logo\.png[^"]*"',
        f'src="cid:{INLINE_LOGO_CID}"',
        html,
        flags=re.I,
    )
    return html


def attach_inline_logo(related_msg: MIMEMultipart, cid: str = INLINE_LOGO_CID) -> bool:
    data = load_logo_bytes()
    if not data:
        return False

    image = MIMEImage(data, _subtype="png")
    image.add_header("Content-ID", f"<{cid}>")
    image.add_header("Content-Disposition", "inline", filename=INLINE_LOGO_FILENAME)
    related_msg.attach(image)
    return True
