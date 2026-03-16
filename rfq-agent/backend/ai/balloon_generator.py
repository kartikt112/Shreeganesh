"""
AI Module: Balloon Generator with Margin-Lane Placement Engine

Places balloon callouts in organized MARGIN LANES around the drawing content
(not on top of dimensions). Each balloon connects to its feature via a leader line.

Strategy:
1. Build occupancy map (binary threshold + dilate + distance transform)
2. Infer content bounding box from feature positions
3. Define margin lanes (TOP, BOTTOM, LEFT, RIGHT) outside the content
4. Assign each feature to the nearest lane
5. Within each lane, sort features and place balloons with even spacing
6. Fine-tune positions using distance transform (avoid stray ink in margins)
7. Draw leader lines from each balloon to its feature
"""
import os
import math
import shutil
from typing import List, Dict, Any, Tuple, Optional

# ── Constants ──────────────────────────────────────────────────────────────
LANE_OFFSET = 50              # Distance from content edge to balloon lane center
MIN_BALLOON_SPACING = 40      # Min pixels between balloon centers in a lane
BALLOON_EDGE_GAP = 8          # Min gap between balloon edges (collision check)
BORDER_MARGIN_PCT = 0.015     # Ignore outer 1.5% (drawing sheet border)
DARK_BLUE = (31, 78, 121)
LIGHT_BLUE = (230, 240, 250)


# ── Phase 1: Occupancy Map ────────────────────────────────────────────────

def _build_occupancy_map(image_path: str):
    """
    Create a free-space map from the drawing image.
    Returns (dist_map, img_h, img_w, title_block_rect).
    """
    import cv2
    import numpy as np

    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"Could not read image: {image_path}")

    img_h, img_w = gray.shape

    # Binary: white pixels (>200) = free, dark = occupied
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # Title block detection: bottom-right region
    tb_y = int(img_h * 0.60)
    tb_x = int(img_w * 0.45)
    title_block_rect = None

    region = binary[tb_y:, tb_x:]
    if region.size > 0:
        ink_ratio = 1.0 - (float(np.sum(region > 200)) / region.size)
        if ink_ratio > 0.05:
            title_block_rect = (tb_x, tb_y, img_w, img_h)
            binary[tb_y:, tb_x:] = 0  # mark title block as occupied

    # Dilate occupied areas by safety margin
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    occupied = cv2.dilate(255 - binary, kernel)
    free_mask = 255 - occupied

    # Distance transform: each free pixel → distance to nearest ink
    dist_map = cv2.distanceTransform(free_mask, cv2.DIST_L2, 5)

    return dist_map, img_h, img_w, title_block_rect


# ── Phase 2: Balloon Size ─────────────────────────────────────────────────

def _compute_radius(img_w: int, img_h: int) -> int:
    """Readable balloon radius — visible but not oversized."""
    return min(30, max(18, min(img_w, img_h) // 100))


# ── Phase 3: Content & Lane Detection ────────────────────────────────────

def _infer_content_bbox(
    features: List[Dict], border: int, img_w: int, img_h: int,
) -> Dict[str, int]:
    """Infer the drawing content area from feature positions."""
    xs, ys = [], []
    for f in features:
        box = f.get("box_2d")
        if box and len(box) == 4:
            ymin, xmin, ymax, xmax = box
            xs.extend([xmin, xmax])
            ys.extend([ymin, ymax])

    if not xs:
        # Fallback: center 60% of the image
        return {
            "xmin": img_w // 5, "ymin": img_h // 5,
            "xmax": 4 * img_w // 5, "ymax": 4 * img_h // 5,
        }

    # Content bbox with small padding
    pad = 30
    return {
        "xmin": max(border, int(min(xs)) - pad),
        "ymin": max(border, int(min(ys)) - pad),
        "xmax": min(img_w - border, int(max(xs)) + pad),
        "ymax": min(img_h - border, int(max(ys)) + pad),
    }


def _define_lanes(
    content: Dict[str, int],
    tb_rect: Optional[Tuple[int, int, int, int]],
    border: int, radius: int,
    img_w: int, img_h: int,
) -> Dict[str, Dict]:
    """
    Define margin lanes around the content area.
    Each lane is either horizontal (fixed Y, variable X) or vertical (fixed X, variable Y).
    """
    lanes = {}

    # TOP lane: above the content
    top_space = content["ymin"] - border
    if top_space > radius * 2 + 10:
        lane_y = border + max(radius + 5, top_space // 2)
        lanes["TOP"] = {
            "axis": "horizontal",
            "fixed": lane_y,
            "range_min": border + radius,
            "range_max": img_w - border - radius,
        }

    # BOTTOM lane: below the content, above title block
    tb_y_limit = (tb_rect[1] - 20) if tb_rect else (img_h - border)
    bottom_space = tb_y_limit - content["ymax"]
    if bottom_space > radius * 2 + 10:
        lane_y = content["ymax"] + min(LANE_OFFSET, bottom_space // 2)
        tb_x_limit = (tb_rect[0] - radius) if tb_rect else (img_w - border - radius)
        lanes["BOTTOM"] = {
            "axis": "horizontal",
            "fixed": lane_y,
            "range_min": border + radius,
            "range_max": tb_x_limit,
        }

    # LEFT lane: left of the content
    left_space = content["xmin"] - border
    if left_space > radius * 2 + 10:
        lane_x = border + max(radius + 5, left_space // 2)
        lanes["LEFT"] = {
            "axis": "vertical",
            "fixed": lane_x,
            "range_min": border + radius,
            "range_max": img_h - border - radius,
        }

    # RIGHT lane: right of the content, left of title block
    tb_x_limit = (tb_rect[0] - 20) if tb_rect else (img_w - border)
    right_space = tb_x_limit - content["xmax"]
    if right_space > radius * 2 + 10:
        lane_x = content["xmax"] + min(LANE_OFFSET, right_space // 2)
        lanes["RIGHT"] = {
            "axis": "vertical",
            "fixed": lane_x,
            "range_min": border + radius,
            "range_max": (tb_rect[1] - radius) if tb_rect else (img_h - border - radius),
        }

    return lanes


def _detect_inter_view_gaps(
    features: List[Dict], content: Dict[str, int], img_w: int,
    border: int, radius: int,
) -> List[Dict]:
    """
    Detect horizontal gaps between views (clusters of features separated vertically).
    Returns additional horizontal lanes in the gaps.
    """
    # Collect Y-centers of all features
    y_centers = []
    for f in features:
        box = f.get("box_2d")
        if box and len(box) == 4:
            y_centers.append((box[0] + box[2]) / 2)

    if len(y_centers) < 4:
        return []

    y_centers.sort()

    gap_lanes = []
    for i in range(len(y_centers) - 1):
        gap = y_centers[i + 1] - y_centers[i]
        if gap > 150:  # Significant gap between views
            gap_y = int((y_centers[i] + y_centers[i + 1]) / 2)
            gap_lanes.append({
                "axis": "horizontal",
                "fixed": gap_y,
                "range_min": border + radius,
                "range_max": img_w - border - radius,
            })

    return gap_lanes


# ── Phase 4: Feature-to-Lane Assignment ──────────────────────────────────

def _assign_zone(
    text_cx: float, text_cy: float,
    content: Dict[str, int],
    tb_rect: Optional[Tuple],
    lanes: Dict[str, Dict],
) -> str:
    """Assign a feature to the nearest available margin lane that can reach it."""
    if not lanes:
        return next(iter(lanes), "TOP")

    best_lane = None
    best_score = -float("inf")

    for lane_name, lane_info in lanes.items():
        if lane_info["axis"] == "horizontal":
            dist = abs(text_cy - lane_info["fixed"])
            # CRITICAL: check if feature's X is within the lane's reachable range
            in_range = lane_info["range_min"] <= text_cx <= lane_info["range_max"]
            # How far outside range is the feature? Heavily penalize out-of-range
            if not in_range:
                overshoot = max(
                    lane_info["range_min"] - text_cx,
                    text_cx - lane_info["range_max"],
                )
            else:
                overshoot = 0
        else:
            dist = abs(text_cx - lane_info["fixed"])
            in_range = lane_info["range_min"] <= text_cy <= lane_info["range_max"]
            if not in_range:
                overshoot = max(
                    lane_info["range_min"] - text_cy,
                    text_cy - lane_info["range_max"],
                )
            else:
                overshoot = 0

        # Score: closer = better, in-range = big bonus, out-of-range = heavy penalty
        score = -dist
        if in_range:
            score += 500
        else:
            score -= overshoot * 3  # 3x penalty per pixel out of range

        # Penalize title-block-adjacent lanes for features far from title block
        if tb_rect:
            if lane_name == "RIGHT" and text_cx < content["xmin"] + (content["xmax"] - content["xmin"]) * 0.3:
                score -= 200
            if lane_name == "BOTTOM" and text_cy < content["ymin"] + (content["ymax"] - content["ymin"]) * 0.3:
                score -= 200

        if score > best_score:
            best_score = score
            best_lane = lane_name

    return best_lane


# ── Phase 5: In-Lane Placement ───────────────────────────────────────────

def _collides_with_placed(
    cx: float, cy: float, radius: int,
    placed: List[Tuple[int, int, int]],
) -> bool:
    """Check if a balloon at (cx, cy) overlaps any already-placed balloon."""
    for bx, by, br in placed:
        dist = math.sqrt((cx - bx) ** 2 + (cy - by) ** 2)
        if dist < radius + br + BALLOON_EDGE_GAP:
            return True
    return False


def _fine_tune_in_lane(
    x: int, y: int,
    lane_info: Dict,
    dist_map, radius: int,
    placed: List[Tuple[int, int, int]],
    img_w: int, img_h: int,
) -> Tuple[int, int]:
    """
    Fine-tune a position within a lane using the distance transform.
    Searches nearby positions for better clearance.
    """
    best_x, best_y = x, y
    best_dt = 0.0

    # Check the primary position and small offsets
    offsets = [0, -15, 15, -30, 30, -50, 50]

    for dx in offsets:
        for dy in offsets:
            cx = x + dx
            cy = y + dy

            # Stay within lane bounds
            if lane_info["axis"] == "horizontal":
                cy = lane_info["fixed"]  # keep Y fixed for horizontal lanes
                if cx < lane_info["range_min"] or cx > lane_info["range_max"]:
                    continue
            else:
                cx = lane_info["fixed"]  # keep X fixed for vertical lanes
                if cy < lane_info["range_min"] or cy > lane_info["range_max"]:
                    continue

            # Bounds check
            if cx - radius < 0 or cx + radius >= img_w:
                continue
            if cy - radius < 0 or cy + radius >= img_h:
                continue

            # Distance transform check
            iy = max(0, min(cy, dist_map.shape[0] - 1))
            ix = max(0, min(cx, dist_map.shape[1] - 1))
            dt_val = float(dist_map[iy, ix])

            if dt_val > best_dt and not _collides_with_placed(cx, cy, radius, placed):
                best_dt = dt_val
                best_x, best_y = cx, cy

    return best_x, best_y


def _place_in_lane(
    lane_name: str,
    lane_features: List[Dict],
    lane_info: Dict,
    dist_map,
    placed: List[Tuple[int, int, int]],
    radius: int,
    img_w: int, img_h: int,
):
    """Place all features assigned to a lane, evenly spaced along the lane axis."""
    if not lane_features:
        return

    # Sort features along the lane's variable axis
    if lane_info["axis"] == "horizontal":
        # Horizontal lane: sort by X position (left to right)
        lane_features.sort(
            key=lambda f: (f["box_2d"][1] + f["box_2d"][3]) / 2
            if f.get("box_2d") and len(f["box_2d"]) == 4 else 0
        )
    else:
        # Vertical lane: sort by Y position (top to bottom)
        lane_features.sort(
            key=lambda f: (f["box_2d"][0] + f["box_2d"][2]) / 2
            if f.get("box_2d") and len(f["box_2d"]) == 4 else 0
        )

    rng_min = lane_info["range_min"]
    rng_max = lane_info["range_max"]
    available = rng_max - rng_min
    n = len(lane_features)

    # Calculate spacing
    total_needed = n * (radius * 2 + BALLOON_EDGE_GAP)
    if total_needed > available:
        # Tight fit: compress spacing
        spacing = max(radius * 2 + 4, available / n)
    else:
        # Even distribution
        spacing = min(available / n, radius * 2 + MIN_BALLOON_SPACING)

    # Center the group in the lane
    group_width = spacing * (n - 1) if n > 1 else 0
    start_pos = rng_min + (available - group_width) / 2

    for i, feat in enumerate(lane_features):
        box = feat.get("box_2d")
        step = int(radius * 2 + BALLOON_EDGE_GAP)

        if lane_info["axis"] == "horizontal":
            # Align balloon X with the feature's X position
            if box and len(box) == 4:
                desired_x = int((box[1] + box[3]) / 2)
            else:
                desired_x = int(start_pos + i * spacing)

            balloon_x = max(rng_min, min(rng_max, desired_x))
            balloon_y = lane_info["fixed"]

            # Resolve collision: try nearby positions, DON'T wrap to opposite end
            attempts = 0
            while _collides_with_placed(balloon_x, balloon_y, radius, placed) and attempts < 20:
                # Alternate left/right of desired position
                offset = (attempts // 2 + 1) * step
                if attempts % 2 == 0:
                    balloon_x = min(rng_max, desired_x + offset)
                else:
                    balloon_x = max(rng_min, desired_x - offset)
                attempts += 1

            # If still colliding, shift to a second row
            if _collides_with_placed(balloon_x, balloon_y, radius, placed):
                balloon_x = max(rng_min, min(rng_max, desired_x))
                if lane_name == "TOP":
                    balloon_y -= step
                else:
                    balloon_y += step

        else:  # vertical lane
            if box and len(box) == 4:
                desired_y = int((box[0] + box[2]) / 2)
            else:
                desired_y = int(start_pos + i * spacing)

            balloon_x = lane_info["fixed"]
            balloon_y = max(rng_min, min(rng_max, desired_y))

            # Resolve collision: try nearby positions
            attempts = 0
            while _collides_with_placed(balloon_x, balloon_y, radius, placed) and attempts < 20:
                offset = (attempts // 2 + 1) * step
                if attempts % 2 == 0:
                    balloon_y = min(rng_max, desired_y + offset)
                else:
                    balloon_y = max(rng_min, desired_y - offset)
                attempts += 1

            if _collides_with_placed(balloon_x, balloon_y, radius, placed):
                balloon_y = max(rng_min, min(rng_max, desired_y))
                if lane_name == "LEFT":
                    balloon_x -= step
                else:
                    balloon_x += step

        # Fine-tune with distance transform
        balloon_x, balloon_y = _fine_tune_in_lane(
            balloon_x, balloon_y, lane_info, dist_map, radius, placed, img_w, img_h
        )

        # Clamp to image bounds
        balloon_x = max(radius, min(img_w - radius, balloon_x))
        balloon_y = max(radius, min(img_h - radius, balloon_y))

        feat["balloon_position"] = [balloon_x, balloon_y]
        feat["balloon_radius"] = radius
        placed.append((balloon_x, balloon_y, radius))


# ── Phase 6: Leader Line ──────────────────────────────────────────────────

def _compute_leader(
    feat: Dict[str, Any],
    balloon_pos: List[int],
    radius: int,
) -> Tuple[Optional[List[int]], Optional[List[int]], Optional[List[int]]]:
    """
    Compute leader line: start (feature location) → optional bend → end (balloon edge).
    """
    bx, by = balloon_pos
    box = feat.get("box_2d")
    anchor = feat.get("anchor_point")

    # Leader start: anchor_point or text center
    if anchor and len(anchor) == 2:
        sx, sy = int(anchor[0]), int(anchor[1])
    elif box and len(box) == 4:
        ymin, xmin, ymax, xmax = box
        sx = int((xmin + xmax) / 2)
        sy = int((ymin + ymax) / 2)
    else:
        return None, None, None

    # Leader end: point on balloon circle nearest to start
    dx = sx - bx
    dy = sy - by
    dist = max(1, math.sqrt(dx * dx + dy * dy))
    ex = int(bx + (dx / dist) * radius)
    ey = int(by + (dy / dist) * radius)

    # If leader is short, no bend needed
    if dist < 60:
        return [sx, sy], None, [ex, ey]

    # Add elbow bend for clean routing
    # Horizontal-first if balloon is more horizontally offset
    if abs(dx) > abs(dy):
        bend = [sx, ey]  # go horizontal from start, then vertical to balloon
    else:
        bend = [ex, sy]  # go vertical from start, then horizontal to balloon

    return [sx, sy], bend, [ex, ey]


# ── Main Entry Points ─────────────────────────────────────────────────────

def place_balloons(
    image_path: str,
    features: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Main placement engine. Organizes balloons in margin lanes around the
    drawing content with leader lines connecting to features.

    Mutates features in-place, adding:
    - balloon_position: [x, y]
    - balloon_radius: int
    - leader_start, leader_bend, leader_end: [x, y] or None
    """
    try:
        dist_map, img_h, img_w, tb_rect = _build_occupancy_map(image_path)
    except Exception as e:
        print(f"[BalloonPlacement] Occupancy map failed: {e}, using fallback")
        _fallback_place_all(features, image_path)
        return features

    radius = _compute_radius(img_w, img_h)
    border = max(50, int(min(img_w, img_h) * BORDER_MARGIN_PCT))

    # Step 1: Compute content bounding box from feature positions
    content = _infer_content_bbox(features, border, img_w, img_h)

    # Step 2: Define margin lanes
    lanes = _define_lanes(content, tb_rect, border, radius, img_w, img_h)

    # Step 3: Add inter-view gap lanes if detected
    gap_lanes = _detect_inter_view_gaps(features, content, img_w, border, radius)
    for i, gl in enumerate(gap_lanes):
        lanes[f"GAP_{i}"] = gl

    if not lanes:
        # No lanes available — fall back to offset placement
        print("[BalloonPlacement] No margin lanes available, using offset fallback")
        _fallback_place_all(features, image_path)
        return features

    # Step 4: Assign features to lanes
    lane_assignments: Dict[str, List[Dict]] = {name: [] for name in lanes}

    for feat in features:
        if not feat.get("balloon_no"):
            continue
        box = feat.get("box_2d")
        if not box or len(box) != 4:
            # No position info — assign to first available lane
            first_lane = next(iter(lanes))
            lane_assignments[first_lane].append(feat)
            continue

        ymin, xmin, ymax, xmax = box
        text_cx = (xmin + xmax) / 2
        text_cy = (ymin + ymax) / 2

        zone = _assign_zone(text_cx, text_cy, content, tb_rect, lanes)
        lane_assignments[zone].append(feat)

    # Step 5: Place balloons in each lane
    placed = []
    for lane_name, lane_feats in lane_assignments.items():
        if lane_feats:
            _place_in_lane(
                lane_name, lane_feats, lanes[lane_name],
                dist_map, placed, radius, img_w, img_h,
            )

    # Step 6: Compute leader lines
    for feat in features:
        pos = feat.get("balloon_position")
        if pos:
            start, bend, end = _compute_leader(feat, pos, radius)
            feat["leader_start"] = start
            feat["leader_bend"] = bend
            feat["leader_end"] = end

    print(f"[BalloonPlacement] Placed {len(placed)} balloons (r={radius}px) in {len(lanes)} lanes on {img_w}x{img_h}")
    return features


def _fallback_place_all(features: List[Dict[str, Any]], image_path: str):
    """Simple offset placement when lane detection fails."""
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        img.close()
    except Exception:
        w, h = 2000, 1500

    radius = _compute_radius(w, h)
    placed = []
    margin = max(60, int(min(w, h) * 0.03))

    for feat in features:
        box = feat.get("box_2d")
        if box and len(box) == 4:
            ymin, xmin, ymax, xmax = box
            text_cx = (xmin + xmax) / 2
            text_cy = (ymin + ymax) / 2
            # Place to the left of the text, pushed toward the margin
            cx = max(margin + radius, int(text_cx) - 80)
            cy = int(text_cy)
        else:
            idx = feat.get("balloon_no", 1) - 1
            cx = margin + radius + (idx % 15) * (radius * 2 + 10)
            cy = margin + radius + (idx // 15) * (radius * 2 + 10)

        cx = max(radius, min(cx, w - radius))
        cy = max(radius, min(cy, h - radius))

        # Resolve collisions
        attempts = 0
        while _collides_with_placed(cx, cy, radius, placed) and attempts < 20:
            cy += radius * 2 + BALLOON_EDGE_GAP
            attempts += 1

        feat["balloon_position"] = [cx, cy]
        feat["balloon_radius"] = radius

        start, bend, end = _compute_leader(feat, [cx, cy], radius)
        feat["leader_start"] = start
        feat["leader_bend"] = bend
        feat["leader_end"] = end
        placed.append((cx, cy, radius))


def ai_place_balloons(
    image_path: str,
    features: List[Dict[str, Any]],
    api_key: str,
) -> List[Dict[str, Any]]:
    """
    Use Claude Vision to determine optimal balloon positions by analyzing the
    actual drawing image. More accurate than algorithmic placement because
    the AI understands drawing context, clear space, and professional conventions.

    Falls back to algorithmic placement if the API call fails.
    """
    import base64
    from PIL import Image

    try:
        from anthropic import Anthropic

        # Load image
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        img = Image.open(image_path)
        img_w, img_h = img.size
        # Detect actual image format from content, not extension
        fmt = img.format  # PIL detects from file header
        fmt_map = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
        media_type = fmt_map.get(fmt, "image/png")
        img.close()

        radius = _compute_radius(img_w, img_h)

        # Build feature list for the prompt
        feat_lines = []
        for f in features:
            bno = f.get("balloon_no")
            spec = f.get("specification", "")[:40]
            box = f.get("box_2d")
            view = f.get("view_name", "")
            if box and len(box) == 4:
                tcx = int((box[1] + box[3]) / 2)
                tcy = int((box[0] + box[2]) / 2)
            else:
                tcx, tcy = 0, 0
            feat_lines.append(f"  #{bno}: \"{spec}\" text_center=({tcx},{tcy}) view=\"{view}\"")

        features_text = "\n".join(feat_lines)

        prompt = f"""You are a Senior Metrology Engineer placing balloon callouts on an engineering drawing.

Image size: {img_w}x{img_h} pixels. Balloon radius: {radius}px.

Features to place balloons for:
{features_text}

RULES:
1. Place each balloon in CLEAR WHITE SPACE — never on dimension text, geometry lines, hatching, or GD&T symbols
2. Balloons should be NEAR their dimension (within 100-400px) — close enough that the association is clear
3. Use margins between views, edges of views, and gaps in the drawing
4. Minimum {radius * 2 + 8}px between any two balloon centers (no overlaps)
5. AVOID the title block (bottom-right) and notes section (bottom-left, below ~60% height)
6. Place balloons in consistent rows/columns where possible for a clean look
7. Each balloon will have a leader line from it to the text_center, so keep them reasonably close

Return ONLY a JSON array, one object per feature:
[{{"n":1,"x":___,"y":___}},{{"n":2,"x":___,"y":___}},...]

where n=balloon_no, x and y are pixel coordinates. No other text."""

        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        response_text = message.content[0].text.strip()

        # Strip markdown fences
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        import json
        import re
        # Try to find JSON array
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            positions = json.loads(match.group())
        else:
            positions = json.loads(response_text)

        # Apply positions
        pos_map = {p["n"]: (p["x"], p["y"]) for p in positions}

        placed = []
        for feat in features:
            bno = feat.get("balloon_no")
            if bno in pos_map:
                x, y = pos_map[bno]
                # Clamp to image bounds
                x = max(radius, min(img_w - radius, int(x)))
                y = max(radius, min(img_h - radius, int(y)))
                feat["balloon_position"] = [x, y]
                feat["balloon_radius"] = radius
                start, bend, end = _compute_leader(feat, [x, y], radius)
                feat["leader_start"] = start
                feat["leader_bend"] = bend
                feat["leader_end"] = end
                placed.append((x, y, radius))

        # Place any features the AI missed using algorithmic fallback
        for feat in features:
            if not feat.get("balloon_position"):
                box = feat.get("box_2d")
                if box and len(box) == 4:
                    cx = int((box[1] + box[3]) / 2) - radius - 30
                    cy = int((box[0] + box[2]) / 2)
                else:
                    cx, cy = 100, 100
                cx = max(radius, min(img_w - radius, cx))
                cy = max(radius, min(img_h - radius, cy))
                while _collides_with_placed(cx, cy, radius, placed):
                    cy += radius * 2 + BALLOON_EDGE_GAP
                feat["balloon_position"] = [cx, cy]
                feat["balloon_radius"] = radius
                start, bend, end = _compute_leader(feat, [cx, cy], radius)
                feat["leader_start"] = start
                feat["leader_bend"] = bend
                feat["leader_end"] = end
                placed.append((cx, cy, radius))

        print(f"[AIPlacement] Placed {len(placed)} balloons via Claude Vision (r={radius}px)")
        return features

    except Exception as e:
        print(f"[AIPlacement] Failed: {e}, falling back to algorithmic placement")
        import traceback
        traceback.print_exc()
        return place_balloons(image_path, features)


def generate_ballooned_image(
    drawing_image_path: str,
    features: List[Dict[str, Any]],
    output_path: str,
    api_key: str = None,
) -> str:
    """
    Draws balloon callouts on the drawing image using pre-computed positions.
    If features don't have balloon_position yet, calls place_balloons() first.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Auto-place if not already placed
        has_positions = any(f.get("balloon_position") for f in features)
        if not has_positions:
            place_balloons(drawing_image_path, features)

        img = Image.open(drawing_image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        radius = _compute_radius(w, h)
        font_size = max(10, int(radius * 0.9))
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=font_size)
        except Exception:
            font = ImageFont.load_default()

        for feat in features:
            num = feat.get("balloon_no")
            if not num:
                continue

            pos = feat.get("balloon_position")
            if not pos or len(pos) != 2:
                continue

            cx, cy = pos[0], pos[1]
            r = feat.get("balloon_radius", radius)

            # Draw leader line
            start = feat.get("leader_start")
            bend = feat.get("leader_bend")
            end = feat.get("leader_end")

            if start and end:
                if bend:
                    draw.line([tuple(start), tuple(bend)], fill=DARK_BLUE, width=1)
                    draw.line([tuple(bend), tuple(end)], fill=DARK_BLUE, width=1)
                else:
                    draw.line([tuple(start), tuple(end)], fill=DARK_BLUE, width=1)
                # Small dot at leader start (on the feature)
                draw.ellipse(
                    [start[0] - 2, start[1] - 2, start[0] + 2, start[1] + 2],
                    fill=DARK_BLUE,
                )

            # Draw balloon circle
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=LIGHT_BLUE, outline=DARK_BLUE, width=1,
            )

            # Draw balloon number
            text = str(num)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                (cx - tw / 2, cy - th / 2 - 1),
                text, fill=DARK_BLUE, font=font,
            )

        img.save(output_path)
        print(f"[BalloonGenerator] Saved: {output_path}")
        return output_path

    except Exception as e:
        print(f"[BalloonGenerator] Error: {e}")
        import traceback
        traceback.print_exc()
        shutil.copy(drawing_image_path, output_path)
        return output_path
