"""
Gemini Balloon Placer — Drop-in replacement for ai_place_balloons().

Uses Gemini's image generation to place numbered inspection balloons on
engineering drawings. Falls back to CV detection → bbox center for misses.

Functions match the existing balloon_generator.py signatures so they can
be swapped in routers/analyze.py without changing anything downstream.
"""
import os
import re
import json
import math
import base64
import traceback
from typing import List, Dict, Any, Tuple, Optional

# Reuse the same visual style
DARK_BLUE = (31, 78, 121)
LIGHT_BLUE = (230, 240, 250)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resize_for_gemini(image_path: str, max_dim: int = 2048) -> Tuple[str, Tuple[int, int]]:
    """Resize image for Gemini API limits. Returns (path, (w, h))."""
    from PIL import Image
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) <= max_dim:
        img.close()
        return image_path, (w, h)

    scale = max_dim / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized_path = image_path.replace(".png", "_gemini_resized.png")
    img.resize((new_w, new_h), Image.LANCZOS).save(resized_path)
    img.close()
    print(f"[GeminiBalloon] Resized {w}x{h} -> {new_w}x{new_h}")
    return resized_path, (new_w, new_h)


def _parse_gemini_coords(text: str) -> List[Dict[str, Any]]:
    """Parse balloon coordinates JSON from Gemini's text response."""
    try:
        match = re.search(r'\[[\s\S]*?\]', text)
        if match:
            coords = json.loads(match.group())
            valid = []
            for c in coords:
                if "balloon_no" in c and "x" in c and "y" in c:
                    valid.append({
                        "balloon_no": int(c["balloon_no"]),
                        "x": float(c["x"]),
                        "y": float(c["y"]),
                    })
            if valid:
                print(f"[GeminiBalloon] Parsed {len(valid)} coords from Gemini JSON")
                return valid
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[GeminiBalloon] Could not parse Gemini JSON: {e}")
    return []


def _detect_circles_cv(image_path: str) -> List[Dict]:
    """Detect circles using OpenCV HoughCircles."""
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
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
        minRadius=min_radius, maxRadius=max_radius,
    )

    results = []
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for cx, cy, r in circles[0, :]:
            results.append({"center": [int(cx), int(cy)], "radius": int(r)})
    return results


def _compute_radius(img_w: int, img_h: int) -> int:
    return max(18, min(35, min(img_w, img_h) // 80))


# ---------------------------------------------------------------------------
# Main: Gemini balloon placement (modifies features in-place)
# ---------------------------------------------------------------------------
def gemini_place_balloons(
    png_path: str,
    features: List[Dict[str, Any]],
    gemini_api_key: str,
    gemini_model: str = None,
) -> Optional[str]:
    """
    Use Gemini to place balloon callouts on a drawing.
    Modifies each feature in-place with: balloon_position, balloon_radius.
    Returns path to Gemini's generated image (for debug), or None.
    """
    from PIL import Image

    if not gemini_model:
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-image")

    orig_img = Image.open(png_path)
    orig_w, orig_h = orig_img.size
    orig_img.close()

    resized_path, resized_size = _resize_for_gemini(png_path)

    # ── Call Gemini ──
    gemini_image_path, gemini_coords = _call_gemini(
        resized_path, features, gemini_api_key, gemini_model, png_path
    )

    if not gemini_image_path and not gemini_coords:
        print("[GeminiBalloon] Gemini failed, falling back to bbox placement")
        _fallback_bbox_placement(features, orig_w, orig_h)
        return None

    # ── Get Gemini output dimensions ──
    gemini_w, gemini_h = resized_size
    if gemini_image_path:
        gi = Image.open(gemini_image_path)
        gemini_w, gemini_h = gi.size
        gi.close()

    # ── Build positions: Gemini JSON → CV fallback → bbox fallback ──
    balloons = _build_balloon_positions(
        gemini_coords, gemini_image_path, features,
        (gemini_w, gemini_h), (orig_w, orig_h),
    )

    # ── Write positions back into features ──
    pos_map = {b["balloon_no"]: b for b in balloons}
    default_radius = _compute_radius(orig_w, orig_h)

    for feat in features:
        bno = feat.get("balloon_no")
        if bno in pos_map:
            b = pos_map[bno]
            feat["balloon_position"] = [int(b["center"][0]), int(b["center"][1])]
            feat["balloon_radius"] = int(b.get("radius", default_radius))
        else:
            # Last-resort: offset from bbox center
            box = feat.get("box_2d")
            if box and len(box) == 4:
                feat["balloon_position"] = [
                    int((box[1] + box[3]) / 2 + default_radius * 2.5),
                    int((box[0] + box[2]) / 2),
                ]
            else:
                feat["balloon_position"] = [50, 50]
            feat["balloon_radius"] = default_radius

    print(f"[GeminiBalloon] Placed {len(balloons)}/{len(features)} balloons")
    return gemini_image_path


def _call_gemini(
    image_path: str,
    features: List[Dict[str, Any]],
    api_key: str,
    model: str,
    original_path: str,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Send image + features to Gemini, get back image + JSON coords."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[GeminiBalloon] google-genai not installed, skipping Gemini")
        return None, []

    import os as _os
    _use_vertex = _os.getenv("GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
    client = genai.Client(vertexai=_use_vertex, api_key=api_key) if _use_vertex else genai.Client(api_key=api_key)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # Build JSON payload
    balloon_json = []
    for feat in features:
        pct = feat.get("bounding_box_pct", [0, 0, 0, 0])
        if not pct or pct == [0, 0, 0, 0]:
            # Derive from box_2d if available
            from PIL import Image as PILImage
            img = PILImage.open(original_path)
            iw, ih = img.size
            img.close()
            box = feat.get("box_2d")
            if box and len(box) == 4:
                pct = [
                    int(box[0] / ih * 1000),
                    int(box[1] / iw * 1000),
                    int(box[2] / ih * 1000),
                    int(box[3] / iw * 1000),
                ]
        balloon_json.append({
            "balloon_no": feat["balloon_no"],
            "specification": feat.get("specification", ""),
            "description": feat.get("description", ""),
            "region": pct,
        })

    json_str = json.dumps(balloon_json, indent=2)
    n = len(features)
    nums = ", ".join(str(f["balloon_no"]) for f in features)

    prompt = f"""You are an expert mechanical engineering drawing annotator.

I need you to place inspection balloons on this engineering drawing. Below is a JSON array of EXACTLY {n} features. Each has a balloon_no and a region hint [ymin, xmin, ymax, xmax] on a 0-1000 grid.

```json
{json_str}
```

YOUR TWO TASKS:

TASK 1 — OUTPUT JSON FIRST:
Before generating the image, output a JSON array listing where you will place each balloon.
Format: [{{"balloon_no": 1, "x": <pixel_x>, "y": <pixel_y>}}, ...]
The x, y must be the CENTER of each balloon circle in the OUTPUT image pixel coordinates.

TASK 2 — GENERATE THE IMAGE:
Then generate the modified drawing with all {n} numbered balloons placed.

RULES:
1. Place EXACTLY {n} balloons — one for EACH entry in the JSON
2. Each balloon MUST show its exact balloon_no number inside the circle
3. Place each balloon in nearby whitespace close to its dimension text
4. Use the "region" hint to locate where each dimension appears
5. Balloons must NOT overlap with each other or drawing geometry
6. Keep the original drawing completely intact — only ADD balloons
7. Standard balloon style: small circle with number centered inside
8. DO NOT skip any balloon — ALL {n} must appear

COUNT CHECK: Output must contain balloons: {nums}

First output the JSON coordinates, then generate the image."""

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            ),
        )

        # Save output dir next to original
        out_dir = os.path.dirname(original_path)
        gemini_output_path = os.path.join(out_dir, "gemini_debug_output.png")
        gemini_coords = []
        gemini_text = ""

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                with open(gemini_output_path, "wb") as f:
                    f.write(part.inline_data.data)
                print(f"[GeminiBalloon] Gemini image saved: {gemini_output_path}")

            if hasattr(part, "text") and part.text:
                gemini_text += part.text

        if gemini_text:
            gemini_coords = _parse_gemini_coords(gemini_text)

        if os.path.exists(gemini_output_path):
            return gemini_output_path, gemini_coords

        print("[GeminiBalloon] WARNING: No image in Gemini response")
        return None, gemini_coords

    except Exception as e:
        print(f"[GeminiBalloon] Gemini API error: {e}")
        traceback.print_exc()
        return None, []


def _build_balloon_positions(
    gemini_coords: List[Dict[str, Any]],
    gemini_image_path: Optional[str],
    features: List[Dict[str, Any]],
    gemini_img_size: Tuple[int, int],
    original_img_size: Tuple[int, int],
) -> List[Dict[str, Any]]:
    """
    Build final balloon positions. Priority:
    1. Gemini's JSON coordinates (scaled to original resolution)
    2. CV detection + nearest-neighbor for missing
    3. Claude's bounding box center for anything still missing
    """
    sx = original_img_size[0] / gemini_img_size[0]
    sy = original_img_size[1] / gemini_img_size[1]

    all_nums = {f["balloon_no"] for f in features}
    placed = {}
    default_radius = _compute_radius(*original_img_size)

    # Priority 1: Gemini JSON coords
    if gemini_coords:
        for gc in gemini_coords:
            bno = gc["balloon_no"]
            if bno in all_nums:
                placed[bno] = {
                    "balloon_no": bno,
                    "center": [gc["x"] * sx, gc["y"] * sy],
                    "radius": default_radius,
                    "source": "gemini_json",
                }

    # Priority 2: CV fallback for missing
    missing = all_nums - set(placed.keys())
    if missing and gemini_image_path:
        cv_balloons = _detect_circles_cv(gemini_image_path)
        cv_scaled = [
            {"center": [b["center"][0] * sx, b["center"][1] * sy], "radius": b["radius"] * max(sx, sy)}
            for b in cv_balloons
        ]

        anchors = []
        for f in features:
            if f["balloon_no"] not in missing:
                continue
            box = f.get("box_2d")
            if box and len(box) == 4:
                anchors.append({
                    "balloon_no": f["balloon_no"],
                    "x": (box[1] + box[3]) / 2,
                    "y": (box[0] + box[2]) / 2,
                })

        # Filter out CV circles near already-placed balloons
        available_cv = []
        for cvb in cv_scaled:
            too_close = any(
                math.sqrt((cvb["center"][0] - p["center"][0])**2 +
                           (cvb["center"][1] - p["center"][1])**2) < default_radius * 3
                for p in placed.values()
            )
            if not too_close:
                available_cv.append(cvb)

        # Greedy nearest-neighbor
        used = set()
        for cvb in available_cv:
            bx, by = cvb["center"]
            best_dist, best_a = float("inf"), None
            for a in anchors:
                if a["balloon_no"] in used:
                    continue
                dist = math.sqrt((bx - a["x"])**2 + (by - a["y"])**2)
                if dist < best_dist:
                    best_dist, best_a = dist, a
            if best_a and best_dist < max(original_img_size) * 0.3:
                placed[best_a["balloon_no"]] = {
                    "balloon_no": best_a["balloon_no"],
                    "center": cvb["center"],
                    "radius": cvb["radius"],
                    "source": "cv_fallback",
                }
                used.add(best_a["balloon_no"])

    # Priority 3: bbox center fallback
    still_missing = all_nums - set(placed.keys())
    for f in features:
        if f["balloon_no"] not in still_missing:
            continue
        box = f.get("box_2d")
        if box and len(box) == 4:
            placed[f["balloon_no"]] = {
                "balloon_no": f["balloon_no"],
                "center": [(box[1] + box[3]) / 2 + default_radius * 2.5, (box[0] + box[2]) / 2],
                "radius": float(default_radius),
                "source": "bbox_fallback",
            }

    return sorted(placed.values(), key=lambda b: b["balloon_no"])


def _fallback_bbox_placement(features: List[Dict[str, Any]], img_w: int, img_h: int):
    """Last resort: place balloons offset from bbox centers."""
    r = _compute_radius(img_w, img_h)
    for feat in features:
        box = feat.get("box_2d")
        if box and len(box) == 4:
            feat["balloon_position"] = [
                int((box[1] + box[3]) / 2 + r * 2.5),
                int((box[0] + box[2]) / 2),
            ]
        else:
            feat["balloon_position"] = [50, 50]
        feat["balloon_radius"] = r


# ---------------------------------------------------------------------------
# Render final image (matches generate_ballooned_image signature)
# ---------------------------------------------------------------------------
def gemini_generate_ballooned_image(
    drawing_image_path: str,
    features: List[Dict[str, Any]],
    output_path: str,
    api_key: str = None,
) -> str:
    """
    Draw balloon callouts on the drawing using pre-computed positions.
    Drop-in replacement for balloon_generator.generate_ballooned_image().
    """
    import shutil
    try:
        from PIL import Image, ImageDraw, ImageFont

        has_positions = any(f.get("balloon_position") for f in features)
        if not has_positions:
            print("[GeminiBalloon] No positions found, skipping render")
            shutil.copy(drawing_image_path, output_path)
            return output_path

        img = Image.open(drawing_image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        radius = _compute_radius(w, h)
        font_size = max(10, int(radius * 0.85))
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=font_size)
        except Exception:
            font = ImageFont.load_default()

        placed = 0
        for feat in features:
            num = feat.get("balloon_no")
            if not num:
                continue

            pos = feat.get("balloon_position")
            if not pos or len(pos) != 2:
                continue

            cx, cy = int(pos[0]), int(pos[1])
            r = int(feat.get("balloon_radius", radius))
            r = max(radius, min(r, radius * 2))

            # Clamp to image bounds
            cx = max(r, min(w - r, cx))
            cy = max(r, min(h - r, cy))

            # Draw balloon circle
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=LIGHT_BLUE, outline=DARK_BLUE, width=2,
            )

            # Draw number
            text = str(num)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - tw / 2, cy - th / 2 - 1), text, fill=DARK_BLUE, font=font)
            placed += 1

        img.save(output_path)
        print(f"[GeminiBalloon] Rendered {placed} balloons → {output_path}")
        return output_path

    except Exception as e:
        print(f"[GeminiBalloon] Render error: {e}")
        traceback.print_exc()
        shutil.copy(drawing_image_path, output_path)
        return output_path
