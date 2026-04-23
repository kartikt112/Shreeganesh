#!/usr/bin/env python3
"""
Test Pipeline: Gemini Image Generation for Balloon Placement
=============================================================
Pipeline:
  1. Extract dimensions using Claude Sonnet 4.6 (assigns balloon numbers)
  2. Send image + feature JSON to Gemini — Gemini returns both:
     a) JSON with balloon_no → (x, y) coordinates
     b) Generated image with balloons
  3. Parse Gemini's JSON coordinates (skip unreliable CV)
  4. Scale Gemini coordinates to original resolution
  5. Validate positions
  6. Draw final balloons with Claude's exact numbering
  7. Verify with Claude — loop until correct
"""

import os
import sys
import json
import time
import math
import base64
import re
import traceback
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-flash-image-preview"

SAMPLE_DRAWING = os.path.join(
    os.path.dirname(__file__),
    "uploads", "drawings", "10_drawing.png"
)
OUTPUT_DIR = "/tmp/gemini_balloon_test"
MAX_RETRIES = 3  # Max verification loops

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def resize_for_gemini(image_path: str, max_dim: int = 2048) -> Tuple[str, Tuple[int, int]]:
    """Resize image for Gemini. Returns (resized_path, (new_w, new_h))."""
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) <= max_dim:
        img.close()
        return image_path, (w, h)

    scale = max_dim / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    resized_path = os.path.join(OUTPUT_DIR, "resized_input.png")
    img_resized.save(resized_path)
    img.close()
    print(f"   Resized {w}x{h} -> {new_w}x{new_h} for Gemini")
    return resized_path, (new_w, new_h)


# =====================================================================
# STAGE 1: Extract dimensions using Claude Sonnet
# =====================================================================
def stage1_extract_dimensions(image_path: str) -> List[Dict[str, Any]]:
    """Use Claude Sonnet to extract dimensional features from drawing."""
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path, override=True)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ANTHROPIC_API_KEY not set. Using mock features for testing.")
        return _mock_features(image_path)

    try:
        from anthropic import Anthropic

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        img = Image.open(image_path)
        img_w, img_h = img.size
        img.close()

        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system="You are a Senior Metrology Engineer reading engineering drawings.",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": """Extract EVERY single dimensional feature and GD&T callout from this engineering drawing. Go view by view: Front view, Section view, Isometric view, Left view — check them ALL.

For each dimension/callout, return:
- balloon_no: sequential number (1, 2, 3, ...)
- specification: exact dimension text as shown on drawing (e.g. "Ø14 ±0.1", "⊙ 0.15 A", "Ra 1.6")
- description: be SPECIFIC and UNIQUE for every entry. For GD&T, state which diameter it belongs to AND its position (e.g. "Concentricity 0.15 A on Ø10.1 section view", "Concentricity 0.15 A on Ø11 left section view", "Concentricity 0.15 A on Ø11 right section view", "Concentricity 0.15 A on Ø12 section view"). For repeated diameters, distinguish by position (left/right/center).
- feature_type: OD/ID/LENGTH/THREAD/CHAMFER/SURFACE_FINISH/RADIUS/ANGLE/GD_T
- bounding_box_pct: [ymin, xmin, ymax, xmax] on 0-1000 normalized grid — must point precisely at THAT specific callout text

CRITICAL RULES:
- EVERY visible dimension text gets its own balloon — no exceptions
- EVERY GD&T frame (⊙, ⊥, //, ◇, △) gets its own balloon — even if the same symbol appears multiple times
- If Ø11 ±0.2 appears TWICE on the drawing, extract BOTH with different bounding_box_pct
- If ⊙ 0.15 A appears FOUR times below four different diameters, extract ALL FOUR as separate entries
- Count your entries at the end — the drawing has approximately 23 features. If you have significantly fewer, you missed some
- bounding_box_pct must be TIGHT around each individual callout text — not a large region

Return ONLY valid JSON array (no markdown):
[{"balloon_no": 1, "specification": "...", "description": "...", "feature_type": "...", "bounding_box_pct": [y0, x0, y1, x1]}]"""}
                ]
            }]
        )

        text = message.content[0].text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            features = json.loads(match.group())
        else:
            features = json.loads(text)

        # Convert normalized coords to absolute pixels
        for f in features:
            pct = f.get("bounding_box_pct")
            if pct and len(pct) == 4:
                f["box_2d"] = [
                    (pct[0] / 1000.0) * img_h,
                    (pct[1] / 1000.0) * img_w,
                    (pct[2] / 1000.0) * img_h,
                    (pct[3] / 1000.0) * img_w
                ]
            f.setdefault("balloon_no", features.index(f) + 1)

        return features

    except Exception as e:
        print(f"   Claude extraction failed: {e}")
        traceback.print_exc()
        return _mock_features(image_path)


def _mock_features(image_path: str) -> List[Dict[str, Any]]:
    """Fallback mock features for testing without Claude API."""
    img = Image.open(image_path)
    w, h = img.size
    img.close()
    return [
        {"balloon_no": 1, "specification": "Ø14 ±0.1", "description": "Outer Dia", "feature_type": "OD",
         "box_2d": [h*0.2, w*0.15, h*0.25, w*0.25], "bounding_box_pct": [200, 150, 250, 250]},
    ]


# =====================================================================
# STAGE 2: Gemini — place balloons AND return JSON coordinates
# =====================================================================
def stage2_gemini_balloon_image(
    image_path: str,
    features: List[Dict[str, Any]],
    resized_size: Tuple[int, int]
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Send drawing + Claude's feature JSON to Gemini.
    Ask Gemini to:
      1. Place numbered balloons on the image
      2. Return JSON with each balloon_no and its (x, y) pixel center

    Returns: (image_path, balloon_coordinates)
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    resized_path, _ = resize_for_gemini(image_path)

    with open(resized_path, "rb") as f:
        image_bytes = f.read()

    # Build JSON payload — Claude's numbering is law
    balloon_json = []
    for f in features:
        pct = f.get("bounding_box_pct", [0, 0, 0, 0])
        balloon_json.append({
            "balloon_no": f["balloon_no"],
            "specification": f.get("specification", ""),
            "description": f.get("description", ""),
            "region": pct
        })

    json_str = json.dumps(balloon_json, indent=2)

    prompt = f"""You are an expert mechanical engineering drawing annotator.

I need you to place inspection balloons on this engineering drawing. Below is a JSON array of EXACTLY {len(features)} features. Each has a balloon_no and a region hint [ymin, xmin, ymax, xmax] on a 0-1000 grid.

```json
{json_str}
```

YOUR TWO TASKS:

TASK 1 — OUTPUT JSON FIRST:
Before generating the image, output a JSON array listing where you will place each balloon.
Format: [{{"balloon_no": 1, "x": <pixel_x>, "y": <pixel_y>}}, ...]
The x, y must be the CENTER of each balloon circle in the OUTPUT image pixel coordinates.

TASK 2 — GENERATE THE IMAGE:
Then generate the modified drawing with all {len(features)} numbered balloons placed.

RULES:
1. Place EXACTLY {len(features)} balloons — one for EACH entry in the JSON
2. Each balloon MUST show its exact balloon_no number inside the circle
3. Place each balloon in nearby whitespace close to its dimension text
4. Use the "region" hint to locate where each dimension appears
5. Balloons must NOT overlap with each other or drawing geometry
6. Keep the original drawing completely intact — only ADD balloons
7. Standard balloon style: small circle with number centered inside
8. DO NOT skip any balloon — ALL {len(features)} must appear

COUNT CHECK: Output must contain balloons: {', '.join(str(f['balloon_no']) for f in features)}

First output the JSON coordinates, then generate the image."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )

        gemini_output_path = os.path.join(OUTPUT_DIR, "gemini_ballooned.png")
        gemini_coords = []
        gemini_text = ""

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                with open(gemini_output_path, "wb") as f:
                    f.write(part.inline_data.data)
                print(f"   Gemini image saved: {gemini_output_path}")

            if hasattr(part, 'text') and part.text:
                gemini_text += part.text
                print(f"   Gemini text: {part.text[:300]}")

        # Parse JSON coordinates from Gemini's text response
        if gemini_text:
            gemini_coords = _parse_gemini_coords(gemini_text)

        if os.path.exists(gemini_output_path):
            return gemini_output_path, gemini_coords

        print("   WARNING: No image in Gemini response")
        return None, []

    except Exception as e:
        print(f"   Gemini API error: {e}")
        traceback.print_exc()
        return None, []


def _parse_gemini_coords(text: str) -> List[Dict[str, Any]]:
    """Parse balloon coordinates JSON from Gemini's text response."""
    try:
        # Find JSON array in the text
        match = re.search(r'\[[\s\S]*?\]', text)
        if match:
            coords = json.loads(match.group())
            # Validate structure
            valid = []
            for c in coords:
                if "balloon_no" in c and "x" in c and "y" in c:
                    valid.append({
                        "balloon_no": int(c["balloon_no"]),
                        "x": float(c["x"]),
                        "y": float(c["y"])
                    })
            if valid:
                print(f"   Parsed {len(valid)} balloon coordinates from Gemini JSON")
                return valid
    except (json.JSONDecodeError, ValueError) as e:
        print(f"   Could not parse Gemini JSON coords: {e}")

    return []


# =====================================================================
# STAGE 3: Build balloon positions (Gemini JSON → CV fallback)
# =====================================================================
def stage3_build_balloon_positions(
    gemini_coords: List[Dict[str, Any]],
    gemini_image_path: str,
    features: List[Dict[str, Any]],
    gemini_img_size: Tuple[int, int],
    original_img_size: Tuple[int, int]
) -> List[Dict[str, Any]]:
    """
    Build final balloon list. Priority:
    1. Use Gemini's JSON coordinates (exact balloon_no → pixel mapping)
    2. Fall back to CV detection + nearest-neighbor for any missing
    3. Fall back to Claude's bounding box center for anything still missing
    """
    sx = original_img_size[0] / gemini_img_size[0]
    sy = original_img_size[1] / gemini_img_size[1]

    all_feature_nums = {f["balloon_no"] for f in features}
    placed = {}  # balloon_no → position dict
    default_radius = max(18, min(35, min(original_img_size) // 80))

    # ── Priority 1: Gemini's own JSON coordinates ──
    if gemini_coords:
        print(f"   Using Gemini JSON coords for {len(gemini_coords)} balloons")
        for gc in gemini_coords:
            bno = gc["balloon_no"]
            if bno in all_feature_nums:
                placed[bno] = {
                    "balloon_no": bno,
                    "center": [gc["x"] * sx, gc["y"] * sy],
                    "radius": default_radius * (max(sx, sy) * 0.25),
                    "source": "gemini_json",
                }

    # ── Priority 2: CV detection for missing balloons ──
    missing_after_json = all_feature_nums - set(placed.keys())
    if missing_after_json and gemini_image_path:
        print(f"   {len(missing_after_json)} balloons missing from JSON, trying CV detection...")
        cv_balloons = _detect_circles_cv(gemini_image_path)

        # Scale CV detections to original space
        cv_scaled = []
        for b in cv_balloons:
            cv_scaled.append({
                "center": [b["center"][0] * sx, b["center"][1] * sy],
                "radius": b["radius"] * max(sx, sy),
            })

        # Build anchors for missing features only
        anchors = []
        for f in features:
            if f["balloon_no"] not in missing_after_json:
                continue
            box = f.get("box_2d")
            if box and len(box) == 4:
                anchors.append({
                    "balloon_no": f["balloon_no"],
                    "x": (box[1] + box[3]) / 2,
                    "y": (box[0] + box[2]) / 2,
                })

        # Filter out CV circles that are near already-placed balloons
        available_cv = []
        for cvb in cv_scaled:
            too_close = False
            for p in placed.values():
                dist = math.sqrt((cvb["center"][0] - p["center"][0])**2 +
                                 (cvb["center"][1] - p["center"][1])**2)
                if dist < default_radius * 3:
                    too_close = True
                    break
            if not too_close:
                available_cv.append(cvb)

        # Greedy nearest-neighbor on remaining
        used_anchors = set()
        for cvb in available_cv:
            bx, by = cvb["center"]
            best_dist = float("inf")
            best_anchor = None
            for a in anchors:
                if a["balloon_no"] in used_anchors:
                    continue
                dist = math.sqrt((bx - a["x"])**2 + (by - a["y"])**2)
                if dist < best_dist:
                    best_dist = dist
                    best_anchor = a
            if best_anchor and best_dist < max(original_img_size) * 0.3:
                placed[best_anchor["balloon_no"]] = {
                    "balloon_no": best_anchor["balloon_no"],
                    "center": cvb["center"],
                    "radius": cvb["radius"],
                    "source": "cv_fallback",
                }
                used_anchors.add(best_anchor["balloon_no"])
                print(f"   CV fallback → #{best_anchor['balloon_no']}")

    # ── Priority 3: Claude bbox center for anything still missing ──
    still_missing = all_feature_nums - set(placed.keys())
    for f in features:
        if f["balloon_no"] not in still_missing:
            continue
        box = f.get("box_2d")
        if box and len(box) == 4:
            cx = (box[1] + box[3]) / 2 + default_radius * 2.5
            cy = (box[0] + box[2]) / 2
            placed[f["balloon_no"]] = {
                "balloon_no": f["balloon_no"],
                "center": [cx, cy],
                "radius": float(default_radius),
                "source": "bbox_fallback",
            }
            spec = f.get("specification", "")
            print(f"   BBOX fallback → #{f['balloon_no']}: {spec}")

    # Add specs
    spec_map = {f["balloon_no"]: f.get("specification", "") for f in features}
    for bno, p in placed.items():
        p["specification"] = spec_map.get(bno, "")

    result = sorted(placed.values(), key=lambda b: b["balloon_no"])
    return result


def _detect_circles_cv(gemini_image_path: str) -> List[Dict]:
    """Detect circles using OpenCV Hough transform."""
    img = cv2.imread(gemini_image_path)
    if img is None:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    min_radius = max(10, min(w, h) // 120)
    max_radius = max(30, min(w, h) // 30)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)

    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=min_radius * 2,
        param1=80, param2=40,
        minRadius=min_radius, maxRadius=max_radius
    )

    results = []
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for cx, cy, r in circles[0, :]:
            results.append({"center": [int(cx), int(cy)], "radius": int(r)})

    # Save debug image
    debug_img = img.copy()
    for b in results:
        cv2.circle(debug_img, tuple(b["center"]), b["radius"], (0, 255, 0), 2)
    cv2.imwrite(os.path.join(OUTPUT_DIR, "detected_balloons_debug.png"), debug_img)

    return results


# =====================================================================
# STAGE 4: Validate balloon positions
# =====================================================================
def stage4_validate(
    balloons: List[Dict[str, Any]],
    features: List[Dict[str, Any]],
    img_size: Tuple[int, int]
) -> Dict[str, Any]:
    """Validate placement: coverage, overlaps, bounds."""
    w, h = img_size
    issues = []
    all_nums = {f["balloon_no"] for f in features}
    placed_nums = {b["balloon_no"] for b in balloons}

    missing = all_nums - placed_nums
    if missing:
        issues.append(f"Missing balloons: {sorted(missing)}")

    extra = placed_nums - all_nums
    if extra:
        issues.append(f"Extra balloons: {sorted(extra)}")

    # Bounds check
    for b in balloons:
        cx, cy = b["center"]
        r = b.get("radius", 20)
        if cx - r < 0 or cy - r < 0 or cx + r > w or cy + r > h:
            issues.append(f"#{b['balloon_no']} out of bounds")

    # Overlap check
    overlaps = 0
    for i, b1 in enumerate(balloons):
        for j, b2 in enumerate(balloons):
            if i >= j:
                continue
            d = math.sqrt((b1["center"][0]-b2["center"][0])**2 +
                          (b1["center"][1]-b2["center"][1])**2)
            r1 = b1.get("radius", 20)
            r2 = b2.get("radius", 20)
            if d < (r1 + r2) * 0.8:
                overlaps += 1

    return {
        "valid": len(issues) == 0 and len(balloons) == len(features),
        "placed": len(balloons),
        "expected": len(features),
        "overlaps": overlaps,
        "missing": sorted(missing),
        "issues": issues,
    }


# =====================================================================
# STAGE 5: Draw final balloons
# =====================================================================
def stage5_draw_final(
    original_image_path: str,
    balloons: List[Dict[str, Any]],
    output_path: str
) -> str:
    """Render clean balloons on original full-res drawing."""
    img = Image.open(original_image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    base_radius = max(18, min(35, min(w, h) // 80))

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(base_radius * 0.85))
    except Exception:
        font = ImageFont.load_default()

    DARK_BLUE = (31, 78, 121)
    LIGHT_BLUE = (230, 240, 250)

    placed = 0
    for b in balloons:
        num = b.get("balloon_no", 0)
        if num == 0:
            continue

        cx, cy = int(b["center"][0]), int(b["center"][1])
        r = int(b.get("radius", base_radius))
        r = max(base_radius, min(r, base_radius * 2))  # Normalize radius

        cx = max(r, min(w - r, cx))
        cy = max(r, min(h - r, cy))

        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=LIGHT_BLUE, outline=DARK_BLUE, width=2)

        text = str(num)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((cx-tw/2, cy-th/2-1), text, fill=DARK_BLUE, font=font)
        placed += 1

    img.save(output_path)
    print(f"   Rendered {placed} balloons")
    return output_path


# =====================================================================
# STAGE 6: Verify with Claude (loop until correct)
# =====================================================================
def stage6_verify_with_claude(
    final_image_path: str,
    features: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Send final image to Claude to verify all balloons are correctly placed."""
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path, override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"verified": False, "error": "No API key"}

    from anthropic import Anthropic

    with open(final_image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    expected = []
    for f in features:
        expected.append(f"#{f['balloon_no']}: {f.get('specification','')} ({f.get('description','')})")
    expected_str = "\n".join(expected)

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": f"""Look at this engineering drawing with numbered inspection balloons (small blue circles with numbers).

Expected balloons:
{expected_str}

VERIFY:
1. Count how many balloons are visible in the image
2. List each balloon number you can see and what dimension it is near
3. List any MISSING balloon numbers (expected but not visible)
4. List any WRONG placements (balloon near the wrong dimension)

Return ONLY JSON (no markdown):
{{"total_visible": <int>, "found_balloons": [<list of balloon numbers you see>], "missing": [<list of missing numbers>], "wrong_placements": [<list of {{balloon_no, issue}}>], "all_correct": <true/false>}}"""}
            ]
        }]
    )

    text = message.content[0].text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]

    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except:
        pass

    return {"verified": False, "raw": text}


# =====================================================================
# MAIN: Run full pipeline with verification loop
# =====================================================================
def run_pipeline(drawing_path: str):
    ensure_dir(OUTPUT_DIR)

    print("\n" + "=" * 65)
    print("  GEMINI BALLOON PIPELINE - TEST RUN")
    print("=" * 65)

    orig_img = Image.open(drawing_path)
    orig_size = orig_img.size
    orig_img.close()
    print(f"\n  Input: {drawing_path}")
    print(f"  Size:  {orig_size[0]}x{orig_size[1]}")

    # ── Stage 1: Claude extraction ──
    print(f"\n{'─'*55}")
    print("  STAGE 1: Extract Dimensions (Claude Sonnet 4.6)")
    print(f"{'─'*55}")
    t0 = time.time()
    features = stage1_extract_dimensions(drawing_path)
    print(f"   Extracted {len(features)} features ({time.time()-t0:.1f}s)")
    for f in features:
        print(f"     #{f.get('balloon_no')}: {f.get('specification')} ({f.get('description')})")

    features_path = os.path.join(OUTPUT_DIR, "extracted_features.json")
    with open(features_path, "w") as fp:
        json.dump(features, fp, indent=2)

    # Get resized dimensions for Gemini
    _, resized_size = resize_for_gemini(drawing_path)

    # ── LOOP: Gemini placement → verify → retry ──
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n{'═'*55}")
        print(f"  ATTEMPT {attempt}/{MAX_RETRIES}")
        print(f"{'═'*55}")

        # ── Stage 2: Gemini placement ──
        print(f"\n{'─'*55}")
        print("  STAGE 2: Gemini Balloon Placement")
        print(f"{'─'*55}")
        t0 = time.time()
        gemini_path, gemini_coords = stage2_gemini_balloon_image(
            drawing_path, features, resized_size
        )
        print(f"   Gemini completed ({time.time()-t0:.1f}s)")

        if not gemini_path:
            print("   FAILED: No image returned. Retrying...")
            continue

        gemini_img = Image.open(gemini_path)
        gemini_size = gemini_img.size
        gemini_img.close()
        print(f"   Gemini output: {gemini_size[0]}x{gemini_size[1]}")
        print(f"   JSON coords received: {len(gemini_coords)}")

        # ── Stage 3: Build positions ──
        print(f"\n{'─'*55}")
        print("  STAGE 3: Build Balloon Positions")
        print(f"{'─'*55}")
        balloons = stage3_build_balloon_positions(
            gemini_coords, gemini_path, features, gemini_size, orig_size
        )
        print(f"   Total balloons: {len(balloons)}")
        sources = {}
        for b in balloons:
            s = b.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1
        for s, c in sources.items():
            print(f"     {s}: {c}")

        for b in balloons:
            print(f"     #{b['balloon_no']}: {b.get('specification','')} "
                  f"at ({b['center'][0]:.0f}, {b['center'][1]:.0f}) [{b.get('source','')}]")

        # ── Stage 4: Validate ──
        print(f"\n{'─'*55}")
        print("  STAGE 4: Validate Positions")
        print(f"{'─'*55}")
        validation = stage4_validate(balloons, features, orig_size)
        print(f"   Placed: {validation['placed']}/{validation['expected']}")
        print(f"   Overlaps: {validation['overlaps']}")
        print(f"   Missing: {validation['missing']}")
        if validation['issues']:
            for issue in validation['issues']:
                print(f"     ⚠ {issue}")
        else:
            print("   ✓ All positions valid!")

        # ── Stage 5: Render ──
        print(f"\n{'─'*55}")
        print("  STAGE 5: Draw Final Balloons")
        print(f"{'─'*55}")
        final_path = os.path.join(OUTPUT_DIR, "final_ballooned.png")
        stage5_draw_final(drawing_path, balloons, final_path)
        print(f"   Final image: {final_path}")

        # ── Stage 6: Verify with Claude ──
        print(f"\n{'─'*55}")
        print("  STAGE 6: Verify with Claude")
        print(f"{'─'*55}")
        t0 = time.time()
        verification = stage6_verify_with_claude(final_path, features)
        print(f"   Verification ({time.time()-t0:.1f}s):")
        print(f"   Visible: {verification.get('total_visible', '?')}")
        print(f"   Found: {verification.get('found_balloons', [])}")
        print(f"   Missing: {verification.get('missing', [])}")
        print(f"   Wrong: {verification.get('wrong_placements', [])}")
        print(f"   All correct: {verification.get('all_correct', False)}")

        # Save verification
        verif_path = os.path.join(OUTPUT_DIR, f"verification_attempt_{attempt}.json")
        with open(verif_path, "w") as fp:
            json.dump(verification, fp, indent=2)

        # Check if we're done
        if verification.get("all_correct", False) and validation["placed"] == validation["expected"]:
            print(f"\n  ✅ ALL {len(features)} BALLOONS CORRECTLY PLACED!")
            break

        # Analyze what went wrong for next attempt
        missing = verification.get("missing", [])
        wrong = verification.get("wrong_placements", [])

        if not missing and not wrong and validation["placed"] == validation["expected"]:
            print(f"\n  ✅ Pipeline validation passed! ({validation['placed']}/{validation['expected']})")
            break

        if attempt < MAX_RETRIES:
            print(f"\n  ⚠ Issues found. Retrying (attempt {attempt+1})...")
            print(f"    Missing: {missing}")
            print(f"    Wrong: {wrong}")
        else:
            print(f"\n  ⚠ Max retries reached. Best result: {validation['placed']}/{validation['expected']}")

    # ── Summary ──
    print(f"\n{'='*65}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*65}")
    print(f"  Outputs in: {OUTPUT_DIR}/")
    print(f"    extracted_features.json  - Claude's feature data")
    print(f"    gemini_ballooned.png     - Gemini's output")
    print(f"    final_ballooned.png      - Final rendered output")
    print(f"{'='*65}\n")

    # Save result
    result_path = os.path.join(OUTPUT_DIR, "pipeline_result.json")
    with open(result_path, "w") as fp:
        json.dump({
            "features": [{k:v for k,v in f.items() if not k.startswith("_")} for f in features],
            "balloons": balloons,
            "validation": validation,
            "verification": verification,
            "gemini_model": GEMINI_MODEL,
            "input_size": list(orig_size),
        }, fp, indent=2, default=str)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test Gemini Balloon Pipeline")
    parser.add_argument("--drawing", default=SAMPLE_DRAWING)
    args = parser.parse_args()

    drawing = args.drawing
    if not os.path.exists(drawing):
        print(f"Drawing not found: {drawing}")
        sys.exit(1)

    run_pipeline(drawing)
