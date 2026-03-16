"""
Analyze Router - Full AI Pipeline:
1. PDF → PNG
2. Feature extraction (Claude Vision)
3. Geometry correction
4. Gemini balloon placement (with retry + Claude verification loop)
5. Render final ballooned image
6. Interactive mode → save draft and stop
7. Feasibility engine → save to DB

Supports ?interactive=true query param to pause at balloon editor.
"""
import os
import sys
import json
import math
import re
import time
import base64
import traceback
import functools
import datetime
from typing import List, Dict, Any, Tuple, Optional

# Force unbuffered stdout so print() appears in server logs immediately
_orig_print = print
print = functools.partial(_orig_print, flush=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai"))

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, UploadFile, File, Request
from sqlalchemy.orm import Session

from database import get_db
from models import RFQ, DrawingFeature, RFQStatus, PipelineRun, PipelineRunStatus
from schemas import RFQOut

router = APIRouter(prefix="/api/rfq", tags=["analyze"])

MAX_BALLOON_RETRIES = 3
DARK_BLUE = (31, 78, 121)
LIGHT_BLUE = (230, 240, 250)
GEMINI_MODEL = "gemini-3.1-flash-image-preview"


# ═══════════════════════════════════════════════════════════════════════════
# Config helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_api_key():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return os.getenv("ANTHROPIC_API_KEY", "")


def _get_gemini_key():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return os.getenv("GEMINI_API_KEY", "")


def _get_image_size(path: str) -> Tuple[int, int]:
    from PIL import Image
    img = Image.open(path)
    size = img.size
    img.close()
    return size


def _compute_radius(img_w: int, img_h: int) -> int:
    return max(18, min(35, min(img_w, img_h) // 80))


def _save_feature_to_db(db, rfq_id: int, feat: dict):
    """Save a feature dict to DB, using whitelist of known DB columns."""
    ALLOWED_KEYS = {
        "balloon_no", "description", "specification", "criticality",
        "feature_type", "proposed_machine", "inhouse_outsource", "feasible",
        "reason_not_feasible", "deviation_required", "box_2d",
        "measuring_instrument", "inspection_inhouse", "inspection_frequency",
        "gauge_required", "remarks",
    }
    box_2d = feat.get("box_2d")
    if isinstance(box_2d, list):
        feat["box_2d"] = json.dumps(box_2d)
    elif box_2d is None or box_2d == "":
        feat["box_2d"] = None

    cleaned = {k: v for k, v in feat.items() if k in ALLOWED_KEYS}
    db.add(DrawingFeature(rfq_id=rfq_id, **cleaned))


# ═══════════════════════════════════════════════════════════════════════════
# Gemini Balloon Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def _resize_for_gemini(image_path: str, output_dir: str, max_dim: int = 2048) -> Tuple[str, Tuple[int, int]]:
    """Resize image for Gemini API limits."""
    from PIL import Image
    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) <= max_dim:
        img.close()
        return image_path, (w, h)

    scale = max_dim / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized_path = os.path.join(output_dir, "resized_input.png")
    img.resize((new_w, new_h), Image.LANCZOS).save(resized_path)
    img.close()
    print(f"[Pipeline] Resized {w}x{h} -> {new_w}x{new_h} for Gemini")
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
                print(f"[Pipeline] Parsed {len(valid)} balloon coords from Gemini JSON")
                return valid
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Pipeline] Could not parse Gemini JSON: {e}")
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


def _gemini_balloon_image(
    image_path: str,
    features: List[Dict[str, Any]],
    gemini_api_key: str,
    output_dir: str,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Send drawing + feature JSON to Gemini.
    Returns: (generated_image_path, balloon_coordinates)
    """
    from google import genai
    from google.genai import types

    gemini_model = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
    client = genai.Client(api_key=gemini_api_key)

    resized_path, _ = _resize_for_gemini(image_path, output_dir)

    with open(resized_path, "rb") as f:
        image_bytes = f.read()

    # Build JSON payload from features
    balloon_json = []
    for feat in features:
        pct = feat.get("bounding_box_pct", [0, 0, 0, 0])
        if not pct or pct == [0, 0, 0, 0]:
            # Derive from box_2d if available
            box = feat.get("box_2d")
            if box and len(box) == 4:
                iw, ih = _get_image_size(image_path)
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
        print(f"[Pipeline] Sending to Gemini model={gemini_model}, {n} features, image={len(image_bytes)} bytes")
        response = client.models.generate_content(
            model=gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            ),
        )

        gemini_output_path = os.path.join(output_dir, "gemini_ballooned.png")
        gemini_coords = []
        gemini_text = ""

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                with open(gemini_output_path, "wb") as f:
                    f.write(part.inline_data.data)
                print(f"[Pipeline] Gemini image saved: {gemini_output_path}")

            if hasattr(part, "text") and part.text:
                gemini_text += part.text
                print(f"[Pipeline] Gemini text: {part.text[:300]}")

        if gemini_text:
            gemini_coords = _parse_gemini_coords(gemini_text)

        if os.path.exists(gemini_output_path):
            return gemini_output_path, gemini_coords

        print("[Pipeline] WARNING: No image in Gemini response")
        return None, gemini_coords

    except Exception as e:
        print(f"[Pipeline] Gemini API error: {e}")
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
    3. bbox center fallback for anything still missing
    """
    sx = original_img_size[0] / gemini_img_size[0]
    sy = original_img_size[1] / gemini_img_size[1]

    all_nums = {f["balloon_no"] for f in features}
    placed = {}
    default_radius = _compute_radius(*original_img_size)

    # Priority 1: Gemini JSON coords
    if gemini_coords:
        print(f"[Pipeline] Using Gemini JSON coords for {len(gemini_coords)} balloons")
        for gc in gemini_coords:
            bno = gc["balloon_no"]
            if bno in all_nums:
                placed[bno] = {
                    "balloon_no": bno,
                    "center": [gc["x"] * sx, gc["y"] * sy],
                    "radius": default_radius * (max(sx, sy) * 0.25),
                    "source": "gemini_json",
                }

    # Priority 2: CV detection for missing
    missing_after_json = all_nums - set(placed.keys())
    if missing_after_json and gemini_image_path:
        print(f"[Pipeline] {len(missing_after_json)} balloons missing from JSON, trying CV...")
        cv_balloons = _detect_circles_cv(gemini_image_path)

        cv_scaled = [
            {"center": [b["center"][0] * sx, b["center"][1] * sy], "radius": b["radius"] * max(sx, sy)}
            for b in cv_balloons
        ]

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

        # Filter CV circles near already-placed balloons
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
                print(f"[Pipeline] CV fallback -> #{best_a['balloon_no']}")

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
            print(f"[Pipeline] BBOX fallback -> #{f['balloon_no']}: {f.get('specification','')}")

    # Add specs
    spec_map = {f["balloon_no"]: f.get("specification", "") for f in features}
    for bno, p in placed.items():
        p["specification"] = spec_map.get(bno, "")

    return sorted(placed.values(), key=lambda b: b["balloon_no"])


def _validate_balloons(
    balloons: List[Dict[str, Any]],
    features: List[Dict[str, Any]],
    img_size: Tuple[int, int],
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

    for b in balloons:
        cx, cy = b["center"]
        r = b.get("radius", 20)
        if cx - r < 0 or cy - r < 0 or cx + r > w or cy + r > h:
            issues.append(f"#{b['balloon_no']} out of bounds")

    overlaps = 0
    for i, b1 in enumerate(balloons):
        for j, b2 in enumerate(balloons):
            if i >= j:
                continue
            d = math.sqrt((b1["center"][0] - b2["center"][0])**2 +
                          (b1["center"][1] - b2["center"][1])**2)
            if d < (b1.get("radius", 20) + b2.get("radius", 20)) * 0.8:
                overlaps += 1

    return {
        "valid": len(issues) == 0 and len(balloons) == len(features),
        "placed": len(balloons),
        "expected": len(features),
        "overlaps": overlaps,
        "missing": sorted(missing),
        "issues": issues,
    }


def _draw_balloons(
    original_image_path: str,
    balloons: List[Dict[str, Any]],
    output_path: str,
) -> str:
    """Render clean balloons on original full-res drawing."""
    from PIL import Image, ImageDraw, ImageFont
    import shutil

    try:
        img = Image.open(original_image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        base_radius = _compute_radius(w, h)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(base_radius * 0.85))
        except Exception:
            font = ImageFont.load_default()

        placed = 0
        for b in balloons:
            num = b.get("balloon_no", 0)
            if num == 0:
                continue

            cx, cy = int(b["center"][0]), int(b["center"][1])
            r = int(b.get("radius", base_radius))
            r = max(base_radius, min(r, base_radius * 2))

            cx = max(r, min(w - r, cx))
            cy = max(r, min(h - r, cy))

            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LIGHT_BLUE, outline=DARK_BLUE, width=2)

            text = str(num)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - tw / 2, cy - th / 2 - 1), text, fill=DARK_BLUE, font=font)
            placed += 1

        img.save(output_path)
        print(f"[Pipeline] Rendered {placed} balloons -> {output_path}")
        return output_path

    except Exception as e:
        print(f"[Pipeline] Render error: {e}")
        traceback.print_exc()
        shutil.copy(original_image_path, output_path)
        return output_path


def _verify_with_claude(
    final_image_path: str,
    features: List[Dict[str, Any]],
    api_key: str,
) -> Dict[str, Any]:
    """Send final image to Claude to verify all balloons are correctly placed."""
    if not api_key:
        return {"verified": False, "error": "No API key"}

    from anthropic import Anthropic

    with open(final_image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    expected = []
    for feat in features:
        expected.append(f"#{feat['balloon_no']}: {feat.get('specification','')} ({feat.get('description','')})")
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
{{"total_visible": <int>, "found_balloons": [<list of balloon numbers you see>], "missing": [<list of missing numbers>], "wrong_placements": [<list of {{"balloon_no": N, "issue": "..."}}>], "all_correct": <true/false>}}"""}
            ]
        }]
    )

    text = message.content[0].text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"verified": False, "raw": text}


def _run_gemini_balloon_pipeline(
    png_path: str,
    features: List[Dict[str, Any]],
    gemini_key: str,
    api_key: str,
    output_dir: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Full Gemini balloon pipeline with retry + Claude verification loop.
    Returns: (balloons_list, ballooned_image_path)
    """
    from PIL import Image

    orig_img = Image.open(png_path)
    orig_size = orig_img.size  # (w, h)
    orig_img.close()

    ballooned_dir = os.path.join(output_dir, "ballooned")
    os.makedirs(ballooned_dir, exist_ok=True)
    drawings_dir = os.path.join(output_dir, "drawings")

    _, resized_size = _resize_for_gemini(png_path, drawings_dir)

    best_balloons = []
    final_path = ""

    for attempt in range(1, MAX_BALLOON_RETRIES + 1):
        print(f"\n[Pipeline] ═══ BALLOON ATTEMPT {attempt}/{MAX_BALLOON_RETRIES} ═══")

        # ── Gemini placement ──
        t0 = time.time()
        gemini_path, gemini_coords = _gemini_balloon_image(
            png_path, features, gemini_key, drawings_dir,
        )
        elapsed = time.time() - t0
        print(f"[Pipeline] Gemini completed ({elapsed:.1f}s)")

        if not gemini_path:
            print("[Pipeline] No image from Gemini, retrying...")
            continue

        gemini_img = Image.open(gemini_path)
        gemini_size = gemini_img.size
        gemini_img.close()
        print(f"[Pipeline] Gemini output: {gemini_size[0]}x{gemini_size[1]}, JSON coords: {len(gemini_coords)}")

        # ── Build positions ──
        balloons = _build_balloon_positions(
            gemini_coords, gemini_path, features, gemini_size, orig_size,
        )
        print(f"[Pipeline] Built {len(balloons)} balloon positions")

        sources = {}
        for b in balloons:
            s = b.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1
        for s, c in sources.items():
            print(f"[Pipeline]   {s}: {c}")

        # ── Validate ──
        validation = _validate_balloons(balloons, features, orig_size)
        print(f"[Pipeline] Validation: {validation['placed']}/{validation['expected']}, overlaps={validation['overlaps']}")
        if validation["issues"]:
            for issue in validation["issues"]:
                print(f"[Pipeline]   ! {issue}")

        # ── Render ──
        final_path = os.path.join(ballooned_dir, "final_ballooned.png")
        _draw_balloons(png_path, balloons, final_path)

        best_balloons = balloons

        # ── Verify with Claude ──
        t0 = time.time()
        verification = _verify_with_claude(final_path, features, api_key)
        print(f"[Pipeline] Claude verification ({time.time() - t0:.1f}s):")
        print(f"[Pipeline]   Visible: {verification.get('total_visible', '?')}")
        print(f"[Pipeline]   Missing: {verification.get('missing', [])}")
        print(f"[Pipeline]   All correct: {verification.get('all_correct', False)}")

        # Save verification
        verif_path = os.path.join(drawings_dir, f"verification_attempt_{attempt}.json")
        with open(verif_path, "w") as fp:
            json.dump(verification, fp, indent=2)

        # Check if done
        if verification.get("all_correct", False) and validation["placed"] == validation["expected"]:
            print(f"[Pipeline] ALL {len(features)} BALLOONS CORRECTLY PLACED!")
            break

        v_missing = verification.get("missing", [])
        v_wrong = verification.get("wrong_placements", [])

        if not v_missing and not v_wrong and validation["placed"] == validation["expected"]:
            print(f"[Pipeline] Validation passed ({validation['placed']}/{validation['expected']})")
            break

        if attempt < MAX_BALLOON_RETRIES:
            print(f"[Pipeline] Issues found, retrying... missing={v_missing}, wrong={v_wrong}")
        else:
            print(f"[Pipeline] Max retries reached. Best: {validation['placed']}/{validation['expected']}")

    return best_balloons, final_path


# ═══════════════════════════════════════════════════════════════════════════
# Main Pipeline (MUST be sync def — not async — so BackgroundTasks runs it
# in a threadpool instead of blocking the event loop)
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(rfq_id: int, interactive: bool = False):
    """
    Background task: run full AI pipeline for an RFQ.
    Records timing and status in PipelineRun for dashboard/metrics.
    """
    from database import SessionLocal

    db = SessionLocal()
    run: PipelineRun | None = None

    try:
        print(f"[Pipeline] ════ Starting pipeline for RFQ {rfq_id} ════")

        rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
        if not rfq:
            print(f"[Pipeline] RFQ {rfq_id} not found")
            return

        # Create run record
        run = PipelineRun(
            rfq_id=rfq_id,
            status=PipelineRunStatus.SUCCESS.value,
            engine="gemini",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        t0_total = time.time()
        stage_times: dict[str, float] = {}

        api_key = _get_api_key()
        gemini_key = _get_gemini_key()
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

        print(
            f"[Pipeline] API keys: anthropic={'yes' if api_key else 'NO'}, "
            f"gemini={'yes' if gemini_key else 'NO'}"
        )

        # ── Step 1: PDF → PNG ─────────────────────────────────────────────
        t0 = time.time()
        rfq.status = RFQStatus.PARSING
        db.commit()
        print(f"[Pipeline] Step 1: PDF -> PNG")

        drawing_path = rfq.drawing_path
        png_path = os.path.join(upload_dir, "drawings", f"{rfq_id}_drawing.png")

        if drawing_path and drawing_path.lower().endswith(".pdf"):
            from drawing_parser import pdf_to_png

            pdf_to_png(drawing_path, png_path)
            print(f"[Pipeline] Converted PDF to PNG: {png_path}")
        elif drawing_path and os.path.exists(drawing_path):
            import shutil

            shutil.copy(drawing_path, png_path)
            print(f"[Pipeline] Copied raster to PNG: {png_path}")
        else:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (800, 600), "white")
            d = ImageDraw.Draw(img)
            d.text((100, 280), "No drawing uploaded - Mock Mode", fill="gray")
            img.save(png_path)
            print(f"[Pipeline] Created mock image")

        rfq.drawing_image_path = f"/uploads/drawings/{rfq_id}_drawing.png"
        db.commit()
        stage_times["pdf_to_png"] = time.time() - t0

        # ── Step 2: Extract features via Claude Vision ────────────────────
        print(f"[Pipeline] Step 2: Claude Vision extraction")
        t0 = time.time()
        manufacturing_metadata = None
        raw_features: list[dict] = []

        if api_key:
            try:
                from vision_extractor import extract_from_image

                print(f"[Pipeline] Calling Claude Vision...")
                extraction_result = extract_from_image(png_path, api_key)
                raw_features = extraction_result.get("features", [])
                manufacturing_metadata = extraction_result.get("manufacturing_metadata", {})

                metadata_path = os.path.join(
                    upload_dir, "drawings", f"{rfq_id}_metadata.json"
                )
                with open(metadata_path, "w") as mf:
                    json.dump(manufacturing_metadata, mf, indent=2)

                print(f"[Pipeline] Extracted {len(raw_features)} features + metadata")
            except Exception as ve:
                print(f"[Pipeline] Vision extractor failed: {ve}")
                traceback.print_exc()
                from drawing_parser import parse_drawing

                raw_features = parse_drawing(
                    png_path, api_key, original_path=drawing_path
                )
        else:
            from drawing_parser import parse_drawing

            raw_features = parse_drawing(png_path, api_key, original_path=drawing_path)

        stage_times["vision_extraction"] = time.time() - t0

        # ── Step 3: Geometry Correction ───────────────────────────────────
        print(f"[Pipeline] Step 3: Geometry correction")
        t0 = time.time()
        from geometry_correction import refine_feature_coordinates

        correction_results = refine_feature_coordinates(png_path, raw_features)

        correction_path = os.path.join(
            upload_dir, "drawings", f"{rfq_id}_corrections.json"
        )
        with open(correction_path, "w") as cf:
            json.dump(correction_results, cf, indent=2)
        print(
            f"[Pipeline] Geometry correction: {len(correction_results)} features refined"
        )
        stage_times["geometry_correction"] = time.time() - t0

        # ── Step 4: Gemini Balloon Pipeline (with retry + verification) ───
        print(f"[Pipeline] Step 4: Balloon placement")
        t0 = time.time()
        rfq.status = RFQStatus.BALLOONING
        db.commit()

        ballooned_path = os.path.join(
            upload_dir, "ballooned", f"{rfq_id}_ballooned.png"
        )
        os.makedirs(os.path.dirname(ballooned_path), exist_ok=True)

        if gemini_key:
            print(
                f"[Pipeline] Using Gemini balloon pipeline (model={GEMINI_MODEL})"
            )
            balloons, temp_final = _run_gemini_balloon_pipeline(
                png_path,
                raw_features,
                gemini_key,
                api_key,
                upload_dir,
            )

            # Write balloon positions back into features
            pos_map = {b["balloon_no"]: b for b in balloons}
            img_w, img_h = _get_image_size(png_path)
            default_radius = _compute_radius(img_w, img_h)
            for feat in raw_features:
                bno = feat.get("balloon_no")
                if bno in pos_map:
                    b = pos_map[bno]
                    r = int(b.get("radius", default_radius))
                    # Clamp balloon center within image bounds
                    bx = max(r, min(img_w - r, int(b["center"][0])))
                    by = max(r, min(img_h - r, int(b["center"][1])))
                    feat["balloon_position"] = [bx, by]
                    feat["balloon_radius"] = r
                    # Set leader line from anchor to balloon edge
                    anchor = feat.get("anchor", feat.get("box_2d_anchor"))
                    if anchor and len(anchor) == 2:
                        feat["leader_start"] = [int(anchor[0]), int(anchor[1])]
                        feat["leader_end"] = [bx, by]
                    else:
                        # Fallback: compute anchor from bounding box center
                        box = feat.get("box_2d")
                        if box and len(box) == 4:
                            ax = int((box[1] + box[3]) / 2)
                            ay = int((box[0] + box[2]) / 2)
                            feat["leader_start"] = [ax, ay]
                            feat["leader_end"] = [bx, by]

            # Copy final rendered image to the RFQ's ballooned path
            if temp_final and os.path.exists(temp_final):
                import shutil

                shutil.copy(temp_final, ballooned_path)
            else:
                _draw_balloons(png_path, balloons, ballooned_path)

            print(f"[Pipeline] Gemini pipeline complete: {len(balloons)} balloons")
        else:
            # Fallback: original Claude pipeline
            print(
                f"[Pipeline] No Gemini key, falling back to Claude balloon placement"
            )
            from balloon_generator import (
                ai_place_balloons,
                generate_ballooned_image,
            )

            ai_place_balloons(png_path, raw_features, api_key)
            generate_ballooned_image(png_path, raw_features, ballooned_path)
            print(
                f"[Pipeline] Claude balloon placement: {len(raw_features)} features"
            )

        stage_times["ballooning"] = time.time() - t0

        # ── Step 5: Save features JSON ────────────────────────────────────
        print(f"[Pipeline] Step 5: Save features JSON")
        t0 = time.time()
        features_path = os.path.join(
            upload_dir, "drawings", f"{rfq_id}_features.json"
        )
        with open(features_path, "w") as fp:
            json.dump(raw_features, fp, indent=2, default=str)
        stage_times["save_features"] = time.time() - t0

        # ── Step 6: Interactive mode → save draft and stop ────────────────
        if interactive:
            print(f"[Pipeline] Step 6: Interactive mode - saving draft")
            t0 = time.time()
            draft_json_path = os.path.join(
                upload_dir, "ballooned", f"{rfq_id}_draft.json"
            )
            draft_output = {
                "features": raw_features,
                "manufacturing_metadata": manufacturing_metadata or {},
            }
            with open(draft_json_path, "w") as df:
                json.dump(draft_output, df, indent=2)

            db.query(DrawingFeature).filter(
                DrawingFeature.rfq_id == rfq_id
            ).delete()
            for feat in raw_features:
                _save_feature_to_db(db, rfq_id, feat)
            db.commit()

            rfq.ballooned_image_path = (
                f"/uploads/ballooned/{rfq_id}_ballooned.png"
            )
            rfq.status = RFQStatus.BALLOONING_REVIEW
            rfq.notes = "interactive_mode=true"
            db.commit()
            print(f"[Pipeline] RFQ {rfq_id} ready for balloon editor review")

            stage_times["interactive_finalize"] = time.time() - t0

            if run:
                run.completed_at = datetime.datetime.utcnow()
                run.total_ms = int((time.time() - t0_total) * 1000)
                run.stages_json = json.dumps(stage_times)
                db.commit()

            return

        # ── Step 7: Feasibility engine ────────────────────────────────────
        print(f"[Pipeline] Step 7: Feasibility engine")
        t0 = time.time()
        from feasibility_engine import process_features

        processed = process_features(
            raw_features, db, manufacturing_metadata=manufacturing_metadata
        )

        db.query(DrawingFeature).filter(
            DrawingFeature.rfq_id == rfq_id
        ).delete()
        for feat in processed:
            _save_feature_to_db(db, rfq_id, feat)
        db.commit()

        rfq.ballooned_image_path = (
            f"/uploads/ballooned/{rfq_id}_ballooned.png"
        )
        rfq.status = RFQStatus.BALLOONING_REVIEW
        db.commit()
        print(f"[Pipeline] RFQ {rfq_id} complete - BALLOONING_REVIEW")
        stage_times["feasibility"] = time.time() - t0

        if run:
            run.completed_at = datetime.datetime.utcnow()
            run.total_ms = int((time.time() - t0_total) * 1000)
            run.stages_json = json.dumps(stage_times)
            db.commit()

    except Exception as e:
        print(f"[Pipeline] ERROR for RFQ {rfq_id}: {e}")
        traceback.print_exc()
        try:
            rfq.status = RFQStatus.NEW
            rfq.notes = f"Pipeline error: {str(e)}"
            db.commit()

            if run:
                run.status = PipelineRunStatus.FAILED.value
                run.failure_message = str(e)
                run.failure_stage = "unknown"
                run.completed_at = run.completed_at or datetime.datetime.utcnow()
                run.total_ms = int(
                    (time.time() - run.started_at.timestamp()) * 1000
                )
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{rfq_id}/analyze")
async def trigger_analysis(
    rfq_id: int,
    background_tasks: BackgroundTasks,
    interactive: bool = Query(False, description="If true, pause at balloon editor instead of auto-proceeding"),
    db: Session = Depends(get_db)
):
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if rfq.status not in [RFQStatus.NEW, RFQStatus.PARSING]:
        raise HTTPException(status_code=400, detail=f"Cannot re-analyze RFQ in status {rfq.status}")

    background_tasks.add_task(run_pipeline, rfq_id, interactive)
    response = {"message": "Analysis started", "rfq_id": rfq_id}
    if interactive:
        response["interactive"] = True
        response["editor_url"] = f"/balloon-editor?rfq_id={rfq_id}"
    return response


@router.get("/{rfq_id}/extraction-data")
async def get_extraction_data(
    rfq_id: int,
    db: Session = Depends(get_db)
):
    """Returns the full extraction data (features + manufacturing_metadata) for the balloon editor."""
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

    # Try draft JSON first (interactive mode)
    draft_path = os.path.join(upload_dir, "ballooned", f"{rfq_id}_draft.json")
    if os.path.exists(draft_path):
        with open(draft_path, "r") as df:
            data = json.load(df)
            data["image_path"] = rfq.drawing_image_path
            data["ballooned_image_path"] = rfq.ballooned_image_path
            return data

    # Fall back to metadata file + DB features
    metadata_path = os.path.join(upload_dir, "drawings", f"{rfq_id}_metadata.json")
    manufacturing_metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as mf:
            manufacturing_metadata = json.load(mf)

    features = db.query(DrawingFeature).filter(
        DrawingFeature.rfq_id == rfq_id
    ).order_by(DrawingFeature.balloon_no).all()

    feature_list = []
    for feat in features:
        f_dict = {
            "balloon_no": feat.balloon_no,
            "description": feat.description,
            "specification": feat.specification,
            "criticality": feat.criticality,
            "feature_type": feat.feature_type,
            "proposed_machine": feat.proposed_machine,
            "inhouse_outsource": feat.inhouse_outsource,
            "feasible": feat.feasible,
            "reason_not_feasible": feat.reason_not_feasible,
            "deviation_required": feat.deviation_required,
            "measuring_instrument": feat.measuring_instrument,
            "inspection_inhouse": feat.inspection_inhouse,
            "inspection_frequency": feat.inspection_frequency,
            "gauge_required": feat.gauge_required,
            "remarks": feat.remarks,
        }
        if feat.box_2d:
            try:
                f_dict["box_2d"] = json.loads(feat.box_2d)
            except json.JSONDecodeError:
                f_dict["box_2d"] = None
        else:
            f_dict["box_2d"] = None
        feature_list.append(f_dict)

    return {
        "features": feature_list,
        "manufacturing_metadata": manufacturing_metadata,
        "image_path": rfq.drawing_image_path,
        "ballooned_image_path": rfq.ballooned_image_path,
    }


@router.post("/{rfq_id}/ballooned-image")
async def upload_ballooned_image(
    rfq_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a rendered ballooned image from the balloon editor."""
    rfq = db.query(RFQ).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    ballooned_dir = os.path.join(upload_dir, "ballooned")
    os.makedirs(ballooned_dir, exist_ok=True)

    balloon_path = os.path.join(ballooned_dir, f"{rfq_id}_ballooned.png")
    with open(balloon_path, "wb") as f:
        content = await file.read()
        f.write(content)

    if not rfq.ballooned_image_path:
        rfq.ballooned_image_path = f"/uploads/ballooned/{rfq_id}_ballooned.png"
        db.commit()

    return {"ok": True, "path": rfq.ballooned_image_path}


@router.post("/{rfq_id}/editor-draft")
async def save_editor_draft(rfq_id: int, request: Request):
    """Save the balloon editor's full state as a draft JSON file."""
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    ballooned_dir = os.path.join(upload_dir, "ballooned")
    os.makedirs(ballooned_dir, exist_ok=True)

    data = await request.json()
    draft_path = os.path.join(ballooned_dir, f"{rfq_id}_draft.json")
    with open(draft_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"ok": True, "message": "Editor draft saved"}
