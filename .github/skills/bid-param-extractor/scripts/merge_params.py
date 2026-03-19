"""Merge extracted product params from multiple chunks into unified product records.

Usage:
    from merge_params import merge_product_params
    merged = merge_product_params(chunk_params_list)

Each element in chunk_params_list is the JSON parsed from chunk.metadata["params_json"].
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def merge_product_params(
    chunk_extractions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge params extracted from multiple chunks into unified product records.

    Groups by (vendor, model) and merges param lists, preferring the most
    detailed value when duplicates are found.

    Args:
        chunk_extractions: List of extraction results, each containing a
            "products" key with a list of product dicts.

    Returns:
        List of merged product dicts with deduplicated params.
    """
    # Collect all products keyed by (vendor, model)
    grouped: Dict[tuple[str, str], Dict[str, Any]] = {}

    for extraction in chunk_extractions:
        products = extraction.get("products", [])
        for product in products:
            vendor = (product.get("vendor") or "").strip()
            model = (product.get("model") or "").strip()
            key = (vendor, model)

            if key not in grouped:
                grouped[key] = {
                    "product_name": product.get("product_name", ""),
                    "model": model,
                    "vendor": vendor,
                    "category": product.get("category", ""),
                    "params": [],
                }

            # Update product_name/category if current is more informative
            existing = grouped[key]
            if len(product.get("product_name", "")) > len(existing["product_name"]):
                existing["product_name"] = product["product_name"]
            if len(product.get("category", "")) > len(existing["category"]):
                existing["category"] = product["category"]

            existing["params"].extend(product.get("params", []))

    # Deduplicate params within each product
    results: List[Dict[str, Any]] = []
    for product in grouped.values():
        product["params"] = _deduplicate_params(product["params"])
        results.append(product)

    return results


def _deduplicate_params(
    params: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Deduplicate params by name, keeping the most detailed value.

    Args:
        params: List of {"name", "value", "unit", "page", "section"} dicts.

    Returns:
        Deduplicated list with longest/most detailed values preserved.
    """
    seen: Dict[str, Dict[str, str]] = {}

    for p in params:
        name = (p.get("name") or "").strip()
        if not name:
            continue

        value = (p.get("value") or "").strip()
        unit = (p.get("unit") or "").strip()
        page = p.get("page", 0)
        section = (p.get("section") or "").strip()

        if name not in seen:
            seen[name] = {
                "name": name, "value": value, "unit": unit,
                "page": page, "section": section,
            }
        else:
            existing = seen[name]
            if len(value) > len(str(existing["value"])):
                existing["value"] = value
                existing["page"] = page
                existing["section"] = section
            if len(unit) > len(str(existing.get("unit", ""))):
                existing["unit"] = unit

    return list(seen.values())


if __name__ == "__main__":
    # Example usage
    test_data = [
        {
            "products": [
                {
                    "product_name": "网络摄像头",
                    "model": "DS-2CD2T47G2-L",
                    "vendor": "海康威视",
                    "category": "摄像头",
                    "params": [
                        {"name": "分辨率", "value": "400万", "unit": "像素"},
                        {"name": "帧率", "value": "25", "unit": "fps"},
                    ],
                }
            ]
        },
        {
            "products": [
                {
                    "product_name": "网络摄像头",
                    "model": "DS-2CD2T47G2-L",
                    "vendor": "海康威视",
                    "category": "摄像头",
                    "params": [
                        {"name": "分辨率", "value": "400万像素 2688×1520", "unit": "像素"},
                        {"name": "防护等级", "value": "IP67", "unit": ""},
                    ],
                }
            ]
        },
    ]

    merged = merge_product_params(test_data)
    print(json.dumps(merged, ensure_ascii=False, indent=2))
