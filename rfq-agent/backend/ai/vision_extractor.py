"""
AI Module: Vision Extractor
Uses Claude Sonnet 4.5 to perform a comprehensive, single-pass visual extraction
of ALL data required for the feasibility report from engineering drawing images.

Replaces PyMuPDF's text coordinate extraction for raster inputs.
Returns both features[] (with box_2d) and manufacturing_metadata{} for the
Feasibility Engine.
"""
import os
import json
import re
import base64
import math
from typing import List, Dict, Any, Tuple, Optional

from prompts.vision_extraction_prompt import VISION_EXTRACTION_PROMPT


def extract_from_image(
    image_path: str,
    api_key: str
) -> Dict[str, Any]:
    """
    Single-pass Claude Vision extraction of dimensions, GD&T, metadata from a drawing image.

    Returns:
        {
            "features": [...],           # List of dimensional features with box_2d
            "manufacturing_metadata": {}  # Title block + material + notes
        }
    """
    from anthropic import Anthropic
    from PIL import Image

    # Step 1: Load image and get pixel dimensions
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    img = Image.open(image_path)
    img_w, img_h = img.size
    # Detect actual format from file header, not extension (extension may lie)
    fmt = img.format or "PNG"
    fmt_map = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif",
               "BMP": "image/bmp", "TIFF": "image/tiff", "WEBP": "image/webp"}
    media_type = fmt_map.get(fmt, "image/png")
    img.close()

    # Step 2: Send to Claude Vision with metrology-specific prompt
    client = Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16384,
        system="You are a Senior Metrology Engineer with decades of experience reading engineering drawings, GD&T symbols, and CNC manufacturing specifications. You perform complete manufacturing feasibility assessments.",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": VISION_EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    if message.stop_reason == "max_tokens":
        print(f"[VisionExtractor] WARNING: Response was truncated (hit max_tokens). JSON may be incomplete.")

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    # Parse JSON — try full object first, then fallback
    result = _parse_extraction_response(response_text)

    # Step 3: Convert normalized bounding box coordinates (0-1000) to absolute pixels
    features = result.get("features", [])
    for f in features:
        pct_box = f.get("bounding_box_pct")
        if pct_box and len(pct_box) == 4:
            ymin = (pct_box[0] / 1000.0) * img_h
            xmin = (pct_box[1] / 1000.0) * img_w
            ymax = (pct_box[2] / 1000.0) * img_h
            xmax = (pct_box[3] / 1000.0) * img_w
            f["box_2d"] = [ymin, xmin, ymax, xmax]
        else:
            f["box_2d"] = None

    # Radial (clock-face) sorting and numbering
    features = _sort_features_radially(features)
    for i, f in enumerate(features):
        f["balloon_no"] = i + 1

    # Update tightest_tolerance balloon_no after re-numbering
    metadata = result.get("manufacturing_metadata", {})
    tightest = metadata.get("tightest_tolerance", {})
    if tightest and tightest.get("feature"):
        for f in features:
            if f.get("specification") == tightest.get("feature"):
                tightest["balloon_no"] = f["balloon_no"]
                break

    # Derive part_envelope if not already populated
    _derive_part_envelope(features, metadata)

    # Find tightest tolerance if not populated
    _derive_tightest_tolerance(features, metadata)

    result["features"] = features
    result["manufacturing_metadata"] = metadata

    print(f"[VisionExtractor] Extracted {len(features)} features + manufacturing metadata.")
    return result


def _parse_extraction_response(text: str) -> Dict[str, Any]:
    """Parse the Claude response into the expected JSON structure."""
    # Try parsing as complete JSON object with both keys
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "features" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Try to find JSON object with regex
    match = re.search(r'\{[\s\S]*"features"[\s\S]*\}', text)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict) and "features" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # Fallback: try to find just the features array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            features = json.loads(match.group())
            return {"features": features, "manufacturing_metadata": _empty_metadata()}
        except json.JSONDecodeError:
            pass

    # Last resort: repair truncated JSON
    # If the response was cut off mid-stream, try to salvage complete features
    repaired = _repair_truncated_json(text)
    if repaired:
        return repaired

    print(f"[VisionExtractor] Failed to parse response. First 200 chars: {text[:200]}")
    return {"features": [], "manufacturing_metadata": _empty_metadata()}


def _repair_truncated_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to repair truncated JSON by finding the last complete feature object
    in the features array and closing the JSON properly.
    """
    # Find the start of the features array
    feat_start = text.find('"features"')
    if feat_start == -1:
        return None

    arr_start = text.find('[', feat_start)
    if arr_start == -1:
        return None

    # Find all complete feature objects by tracking matching braces
    last_complete_end = -1
    depth = 0
    i = arr_start + 1
    while i < len(text):
        ch = text[i]
        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_complete_end = i
        elif ch == '"':
            # Skip string contents (handle escaped quotes)
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == '\\':
                    i += 1  # skip escaped char
                i += 1
        i += 1

    if last_complete_end == -1:
        return None

    # Build a valid JSON with all complete features
    truncated_features = text[arr_start:last_complete_end + 1] + ']'
    try:
        features = json.loads(truncated_features)
        print(f"[VisionExtractor] Repaired truncated JSON — recovered {len(features)} features")

        # Try to also recover manufacturing_metadata if present before truncation
        metadata = _empty_metadata()
        meta_match = re.search(r'"manufacturing_metadata"\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text)
        if meta_match:
            try:
                metadata = json.loads(meta_match.group(1))
            except json.JSONDecodeError:
                pass

        return {"features": features, "manufacturing_metadata": metadata}
    except json.JSONDecodeError:
        return None


def _empty_metadata() -> Dict[str, Any]:
    """Return an empty manufacturing_metadata structure."""
    return {
        "part_name": "",
        "drawing_number": "",
        "material": {
            "grade": "",
            "standard": "",
            "heat_treatment": "",
            "tensile_strength_mpa": None,
            "yield_strength_mpa": None,
            "hardness": None,
            "elongation_pct": None,
        },
        "surface_protection": {
            "method": "",
            "standard": "",
            "code": "",
            "salt_spray_hours": None,
            "salt_spray_standard": None,
        },
        "part_envelope": {
            "max_od_mm": None,
            "max_id_mm": None,
            "total_length_mm": None,
            "is_hollow": False,
        },
        "tightest_tolerance": {
            "value_mm": None,
            "feature": "",
            "balloon_no": None,
        },
        "general_tolerance_standard": "",
        "general_tolerances": {"linear": [], "angular": []},
        "notes": [],
        "production_type": "",
        "scale": "",
        "sheet_size": "",
        "issue_date": "",
        "ern_number": "",
        "unspecified_corner_radii_mm": None,
        "dimensions_after_surface_treatment": False,
    }


def _sort_features_radially(features: List[Dict]) -> List[Dict]:
    """
    Sort features per-view in reading order (top-to-bottom, left-to-right).
    Views are ordered: Front first, then alphabetically.
    """
    if not features:
        return features

    valid = [f for f in features if f.get("box_2d") and len(f["box_2d"]) == 4]
    invalid = [f for f in features if not f.get("box_2d") or len(f.get("box_2d", [])) != 4]

    if not valid:
        return features

    # Group by view_name
    views: Dict[str, List[Dict]] = {}
    no_view: List[Dict] = []
    for f in valid:
        vn = f.get("view_name")
        if vn:
            views.setdefault(vn, []).append(f)
        else:
            no_view.append(f)

    def _reading_order_key(f):
        box = f["box_2d"]
        cy = (box[0] + box[2]) / 2
        cx = (box[1] + box[3]) / 2
        # Quantize Y into rows (~100px) to group horizontally-adjacent features
        return (int(cy / 100), cx)

    # Sort within each view by reading order
    for vn in views:
        views[vn].sort(key=_reading_order_key)

    # If no view_name on any feature, sort all by reading order
    if not views:
        no_view.sort(key=_reading_order_key)
        return no_view + invalid

    # Order views: "Front" first, then alphabetically
    view_order = sorted(views.keys(),
                        key=lambda v: (0 if "front" in v.lower() else 1, v))

    result = []
    for vn in view_order:
        result.extend(views[vn])
    result.extend(no_view)
    result.extend(invalid)
    return result


def _derive_part_envelope(features: List[Dict], metadata: Dict):
    """Derive max OD, max ID, total length from features if not already populated."""
    envelope = metadata.get("part_envelope", {})

    if not envelope.get("max_od_mm"):
        max_od = 0.0
        for f in features:
            if f.get("feature_type") == "OD" and f.get("nominal_value"):
                try:
                    val = float(f["nominal_value"])
                    if val > max_od:
                        max_od = val
                except (ValueError, TypeError):
                    pass
        if max_od > 0:
            envelope["max_od_mm"] = max_od

    if not envelope.get("max_id_mm"):
        max_id = 0.0
        has_id = False
        for f in features:
            if f.get("feature_type") == "ID" and f.get("nominal_value"):
                has_id = True
                try:
                    val = float(f["nominal_value"])
                    if val > max_id:
                        max_id = val
                except (ValueError, TypeError):
                    pass
        if has_id and max_id > 0:
            envelope["max_id_mm"] = max_id
            envelope["is_hollow"] = True

    metadata["part_envelope"] = envelope


def _derive_tightest_tolerance(features: List[Dict], metadata: Dict):
    """Find the tightest tolerance among features if not already populated."""
    tightest = metadata.get("tightest_tolerance", {})
    if tightest.get("value_mm"):
        return

    min_band = float("inf")
    min_feature = None
    for f in features:
        band = f.get("tolerance_band")
        if band is not None:
            try:
                band_val = float(band)
                if 0 < band_val < min_band:
                    min_band = band_val
                    min_feature = f
            except (ValueError, TypeError):
                pass

    if min_feature:
        metadata["tightest_tolerance"] = {
            "value_mm": min_band,
            "feature": min_feature.get("specification", ""),
            "balloon_no": min_feature.get("balloon_no"),
        }
