import numpy as np
import math
from typing import List, Dict, Any, Tuple, Optional

LANE_OFFSET = 50
MIN_BALLOON_SPACING = 40
BALLOON_EDGE_GAP = 8
BORDER_MARGIN_PCT = 0.015

def _infer_content_bbox(features: List[Dict], border: int, img_w: int, img_h: int) -> Dict[str, int]:
    xs, ys = [], []
    for f in features:
        box = f.get("bbox")
        if box and len(box) == 4:
            y1, x1, y2, x2 = box
            xs.extend([x1, x2])
            ys.extend([y1, y2])

    if not xs:
        return {
            "xmin": img_w // 5, "ymin": img_h // 5,
            "xmax": 4 * img_w // 5, "ymax": 4 * img_h // 5,
        }

    pad = 30
    return {
        "xmin": max(border, int(min(xs)) - pad),
        "ymin": max(border, int(min(ys)) - pad),
        "xmax": min(img_w - border, int(max(xs)) + pad),
        "ymax": min(img_h - border, int(max(ys)) + pad),
    }

def _define_lanes(content: Dict[str, int], tb_rect: Optional[Tuple], border: int, radius: int, img_w: int, img_h: int) -> Dict[str, Dict]:
    lanes = {}

    # TOP
    top_space = content["ymin"] - border
    if top_space > radius * 2 + 10:
        lane_y = border + max(radius + 5, top_space // 2)
        lanes["TOP"] = {
            "axis": "horizontal", "fixed": lane_y,
            "range_min": border + radius, "range_max": img_w - border - radius
        }

    # BOTTOM
    tb_y_limit = (tb_rect[1] - 20) if tb_rect else (img_h - border)
    bottom_space = tb_y_limit - content["ymax"]
    if bottom_space > radius * 2 + 10:
        lane_y = content["ymax"] + min(LANE_OFFSET, bottom_space // 2)
        tb_x_limit = (tb_rect[0] - radius) if tb_rect else (img_w - border - radius)
        lanes["BOTTOM"] = {
            "axis": "horizontal", "fixed": lane_y,
            "range_min": border + radius, "range_max": tb_x_limit
        }

    # LEFT
    left_space = content["xmin"] - border
    if left_space > radius * 2 + 10:
        lane_x = border + max(radius + 5, left_space // 2)
        lanes["LEFT"] = {
            "axis": "vertical", "fixed": lane_x,
            "range_min": border + radius, "range_max": img_h - border - radius
        }

    # RIGHT
    tb_x_limit = (tb_rect[0] - 20) if tb_rect else (img_w - border)
    right_space = tb_x_limit - content["xmax"]
    if right_space > radius * 2 + 10:
        lane_x = content["xmax"] + min(LANE_OFFSET, right_space // 2)
        lanes["RIGHT"] = {
            "axis": "vertical", "fixed": lane_x,
            "range_min": border + radius, "range_max": (tb_rect[1] - radius) if tb_rect else (img_h - border - radius)
        }

    return lanes

def _assign_zone(text_cx: float, text_cy: float, content: Dict[str, int], tb_rect: Optional[Tuple], lanes: Dict[str, Dict]) -> str:
    if not lanes: return next(iter(lanes), "TOP")

    best_lane = None
    best_score = -float("inf")

    for lane_name, lane_info in lanes.items():
        if lane_info["axis"] == "horizontal":
            dist = abs(text_cy - lane_info["fixed"])
            in_range = lane_info["range_min"] <= text_cx <= lane_info["range_max"]
            overshoot = 0 if in_range else max(lane_info["range_min"] - text_cx, text_cx - lane_info["range_max"])
        else:
            dist = abs(text_cx - lane_info["fixed"])
            in_range = lane_info["range_min"] <= text_cy <= lane_info["range_max"]
            overshoot = 0 if in_range else max(lane_info["range_min"] - text_cy, text_cy - lane_info["range_max"])

        score = -dist
        if in_range:
            score += 500
        else:
            score -= overshoot * 3

        if tb_rect:
            if lane_name == "RIGHT" and text_cx < content["xmin"] + (content["xmax"] - content["xmin"]) * 0.3:
                score -= 200
            if lane_name == "BOTTOM" and text_cy < content["ymin"] + (content["ymax"] - content["ymin"]) * 0.3:
                score -= 200

        if score > best_score:
            best_score = score
            best_lane = lane_name

    return best_lane

def _collides_with_placed(cx: float, cy: float, radius: int, placed: List[Tuple[int, int, int]]) -> bool:
    for bx, by, br in placed:
        dist = math.sqrt((cx - bx) ** 2 + (cy - by) ** 2)
        if dist < radius + br + BALLOON_EDGE_GAP:
            return True
    return False

def _fine_tune_in_lane(x: int, y: int, lane_info: Dict, dist_map: np.ndarray, radius: int, placed: List, img_w: int, img_h: int) -> Tuple[int, int]:
    best_x, best_y = x, y
    best_dt = 0.0

    offsets = [0, -15, 15, -30, 30, -50, 50]

    for dx in offsets:
        for dy in offsets:
            cx, cy = x + dx, y + dy

            if lane_info["axis"] == "horizontal":
                cy = lane_info["fixed"]
                if not (lane_info["range_min"] <= cx <= lane_info["range_max"]): continue
            else:
                cx = lane_info["fixed"]
                if not (lane_info["range_min"] <= cy <= lane_info["range_max"]): continue

            if cx - radius < 0 or cx + radius >= img_w or cy - radius < 0 or cy + radius >= img_h:
                continue

            iy = max(0, min(int(cy), dist_map.shape[0] - 1))
            ix = max(0, min(int(cx), dist_map.shape[1] - 1))
            dt_val = float(dist_map[iy, ix])

            if dt_val > best_dt and not _collides_with_placed(cx, cy, radius, placed):
                best_dt = dt_val
                best_x, best_y = cx, cy

    return best_x, best_y

def compute_balloon_layout(
    occupancy_data: Tuple[np.ndarray, np.ndarray, int, int, Any], 
    features: List[Dict[str, Any]], 
    radius: int
) -> List[Dict[str, Any]]:
    """
    Step 10: Sequential Balloon Placement (Margin-Lane Engine)
    Organizes balloons neatly around the borders of the drawing workspace.
    """
    dist_map, occupied, img_h, img_w, tb_rect = occupancy_data
    border = max(50, int(min(img_w, img_h) * BORDER_MARGIN_PCT))

    content = _infer_content_bbox(features, border, img_w, img_h)
    lanes = _define_lanes(content, tb_rect, border, radius, img_w, img_h)

    if not lanes:
        print("[Layout Engine] No explicit lanes found, using fallback")
        lanes["TOP"] = {"axis": "horizontal", "fixed": border + radius, "range_min": border + radius, "range_max": img_w - border - radius}

    lane_assignments: Dict[str, List[Dict]] = {name: [] for name in lanes}

    for feat in features:
        box = feat.get("bbox")
        if box and len(box) == 4:
            y1, x1, y2, x2 = box
            text_cx = (x1 + x2) / 2
            text_cy = (y1 + y2) / 2
            zone = _assign_zone(text_cx, text_cy, content, tb_rect, lanes)
        else:
            zone = next(iter(lanes))
        lane_assignments[zone].append(feat)

    placed = []

    for lane_name, lane_feats in lane_assignments.items():
        if not lane_feats: continue
        lane_info = lanes[lane_name]

        # Sort lane features logically
        if lane_info["axis"] == "horizontal":
            lane_feats.sort(key=lambda f: f.get("anchor", [0,0])[0])
        else:
            lane_feats.sort(key=lambda f: f.get("anchor", [0,0])[1])

        rng_min = lane_info["range_min"]
        rng_max = lane_info["range_max"]
        available = rng_max - rng_min
        n = len(lane_feats)

        total_needed = n * (radius * 2 + BALLOON_EDGE_GAP)
        spacing = max(radius * 2 + 4, available / n) if total_needed > available else min(available / n, radius * 2 + MIN_BALLOON_SPACING)

        group_width = spacing * (n - 1) if n > 1 else 0
        start_pos = rng_min + (available - group_width) / 2

        for i, feat in enumerate(lane_feats):
            step = int(radius * 2 + BALLOON_EDGE_GAP)

            if lane_info["axis"] == "horizontal":
                desired_x = int(feat.get("anchor", [start_pos + i*spacing, 0])[0])
                bx = max(rng_min, min(rng_max, desired_x))
                by = lane_info["fixed"]

                attempts = 0
                while _collides_with_placed(bx, by, radius, placed) and attempts < 20:
                    offset = (attempts // 2 + 1) * step
                    bx = min(rng_max, desired_x + offset) if attempts % 2 == 0 else max(rng_min, desired_x - offset)
                    attempts += 1
                    
                if _collides_with_placed(bx, by, radius, placed):
                    bx = max(rng_min, min(rng_max, desired_x))
                    by += -step if lane_name == "TOP" else step
            else:
                desired_y = int(feat.get("anchor", [0, start_pos + i*spacing])[1])
                bx = lane_info["fixed"]
                by = max(rng_min, min(rng_max, desired_y))

                attempts = 0
                while _collides_with_placed(bx, by, radius, placed) and attempts < 20:
                    offset = (attempts // 2 + 1) * step
                    by = min(rng_max, desired_y + offset) if attempts % 2 == 0 else max(rng_min, desired_y - offset)
                    attempts += 1
                    
                if _collides_with_placed(bx, by, radius, placed):
                    by = max(rng_min, min(rng_max, desired_y))
                    bx += -step if lane_name == "LEFT" else step

            # Fine tune
            bx, by = _fine_tune_in_lane(bx, by, lane_info, dist_map, radius, placed, img_w, img_h)

            bx = max(radius, min(img_w - radius, bx))
            by = max(radius, min(img_h - radius, by))

            feat["balloon_position"] = [bx, by]
            feat["balloon_radius"] = radius
            placed.append((bx, by, radius))
            
            # Simple leader logic mapping (actual render will trace this)
            feat["leader_start"] = feat.get("anchor", [0,0])
            feat["leader_end"] = [bx, by]

    return features
