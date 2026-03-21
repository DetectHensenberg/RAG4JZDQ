"""Infer product vendor and model from filenames.

Used at ingestion time to auto-populate product_vendor / product_model
metadata, and at search time as a fallback when metadata is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

# Known vendor prefixes mapped to display names.
# Longest-prefix match is tried first (3 parts, then 2, then 1).
VENDOR_MAP: Dict[str, str] = {
    "dellemc": "Dell EMC",
    "dell": "Dell",
    "hp": "HP",
    "hpe": "HPE",
    "huawei": "华为",
    "hikvision": "海康威视",
    "dahua": "大华",
    "h3c": "新华三",
    "cisco": "Cisco",
    "lenovo": "联想",
    "inspur": "浪潮",
    "sugon": "曙光",
    "zte": "中兴",
    "ruijie": "锐捷",
    "sangfor": "深信服",
    "uniview": "宇视",
    "ezviz": "萤石",
    "tplink": "TP-Link",
    "dlink": "D-Link",
    "supermicro": "Supermicro",
    "ibm": "IBM",
    "juniper": "Juniper",
    "fortinet": "Fortinet",
    "paloalto": "Palo Alto",
    "aruba": "Aruba",
    "asus": "ASUS",
    "apc": "APC",
    "eaton": "Eaton",
    "nsfocus": "绿盟",
    "venustech": "启明星辰",
    "topsec": "天融信",
    "dptech": "迪普",
    "hillstone": "山石网科",
}

_NOISE_TOKENS = frozenset({
    "SPEC-SHEET", "DATASHEET", "BROCHURE", "USER-GUIDE", "MANUAL",
    "QUICK-START", "INSTALLATION", "GUIDE", "SPEC", "SHEET",
    "(1)", "(2)", "(3)", "(4)", "(5)",
})


def infer_from_filename(filename: str) -> tuple[str, str]:
    """Infer vendor and model from a product filename.

    Args:
        filename: Original filename (e.g. ``dellemc-poweredge-r750xs-spec-sheet.pdf``).

    Returns:
        ``(vendor, model)`` tuple. Either or both may be empty strings.
    """
    if not filename:
        return "", ""
    stem = Path(filename).stem.lower().replace(" ", "-").replace("_", "-")
    parts = stem.split("-")

    vendor = ""
    model_start = 0
    for length in (3, 2, 1):
        if length > len(parts):
            continue
        prefix = "-".join(parts[:length])
        if prefix in VENDOR_MAP:
            vendor = VENDOR_MAP[prefix]
            model_start = length
            break

    if model_start >= len(parts):
        return vendor, ""

    model = "-".join(parts[model_start:]).upper()
    for noise in _NOISE_TOKENS:
        model = model.replace(noise, "")
    model = model.strip("-").strip()
    return vendor, model
