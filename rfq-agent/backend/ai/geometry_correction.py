"""
AI Module: Geometry Correction Layer
Uses OpenCV to refine AI-estimated bounding box coordinates from Claude Vision.
Operates between extraction and balloon generation in the pipeline.

The 6-step correction pipeline:
1. Text box refinement - tighten bounding boxes to actual character contours
2. Snap-to-text correction - snap drifted anchors to nearest text clusters
3. Leader line detection - detect dimension leader lines for better anchoring
4. Geometry detection - associate features with circles/lines in the drawing
5. Balloon placement - compute anchor points with offset from text
6. Collision avoidance - prevent balloon overlaps

Input:  features list with box_2d = [ymin, xmin, ymax, xmax] (absolute pixels)
Output: list of corrected feature dicts with corrected_box and anchor_point
"""
import os
import math
from typing import List, Dict, Any, Tuple, Optional


# ── Constants ──────────────────────────────────────────────────────────────

TEXT_CROP_PADDING = 30          # Padding around AI box for text refinement
SNAP_SEARCH_RADIUS = 50        # Search radius for snap-to-text
CANNY_LOW = 50                 # Canny edge detection low threshold
CANNY_HIGH = 150               # Canny edge detection high threshold
LEADER_LINE_THRESHOLD = 40     # HoughLinesP vote threshold for leaders
LEADER_MIN_LINE_LENGTH = 20    # Minimum leader line length
LEADER_MAX_LINE_GAP = 10       # Maximum gap in leader lines
HOUGH_CIRCLES_DP = 1.2         # Inverse ratio of accumulator resolution
HOUGH_CIRCLES_MIN_DIST = 30    # Minimum distance between circle centers
HOUGH_CIRCLES_PARAM1 = 100     # Canny high threshold for HoughCircles
HOUGH_CIRCLES_PARAM2 = 30      # Accumulator threshold for circle centers
HOUGH_CIRCLES_MIN_RADIUS = 10  # Minimum circle radius
HOUGH_CIRCLES_MAX_RADIUS = 300 # Maximum circle radius
BALLOON_OFFSET_PX = 40         # Pixel offset from text box for balloon anchor
BALLOON_DIAMETER = 26           # Matches max radius=20 from balloon_generator
COLLISION_DISTANCE_THRESHOLD = 40   # Minimum distance between balloon centers
COLLISION_SHIFT_PX = 45        # Shift amount on collision (30-50 range midpoint)
SHIFT_DIRECTIONS = [(0, -1), (0, 1), (-1, 0), (1, 0)]  # up, down, left, right

# Feature type → output type mapping
TYPE_MAP = {
    "OD": "dimension", "ID": "dimension", "LENGTH": "dimension",
    "THREAD": "thread", "CHAMFER": "chamfer", "SURFACE_FINISH": "surface",
    "RADIUS": "dimension", "ANGLE": "dimension", "GDT": "gdt",
    "REFERENCE": "reference", "NOTE": "note", "OTHER": "other",
}


# ── Helper Functions ───────────────────────────────────────────────────────

def _box2d_to_xyxy(box_2d: List[float]) -> Tuple[int, int, int, int]:
    """Convert [ymin, xmin, ymax, xmax] to (x1, y1, x2, y2) integers."""
    ymin, xmin, ymax, xmax = box_2d
    return int(xmin), int(ymin), int(xmax), int(ymax)


def _xyxy_to_box2d(x1: int, y1: int, x2: int, y2: int) -> List[int]:
    """Convert (x1, y1, x2, y2) back to [ymin, xmin, ymax, xmax]."""
    return [y1, x1, y2, x2]


def _clamp_box(x1: int, y1: int, x2: int, y2: int,
               img_w: int, img_h: int) -> Tuple[int, int, int, int]:
    """Clamp coordinates to image boundaries."""
    return (
        max(0, min(x1, img_w - 1)),
        max(0, min(y1, img_h - 1)),
        max(0, min(x2, img_w)),
        max(0, min(y2, img_h)),
    )


def _feature_type_to_correction_type(feature_type: str) -> str:
    """Map feature_type (OD, LENGTH, THREAD...) to output 'type' field."""
    return TYPE_MAP.get(feature_type, "dimension")


def _euclidean_distance(p1: Tuple[float, float],
                        p2: Tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _passthrough(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return features in output format without any correction (fallback)."""
    results = []
    for feat in features:
        box_2d = feat.get("box_2d")
        if box_2d and isinstance(box_2d, list) and len(box_2d) == 4:
            x1, y1, x2, y2 = _box2d_to_xyxy(box_2d)
            corrected_box = [x1, y1, x2, y2]
            anchor_point = [(x1 + x2) // 2, (y1 + y2) // 2]
        else:
            corrected_box = None
            anchor_point = None

        results.append({
            "balloon_no": feat.get("balloon_no"),
            "spec": feat.get("specification", ""),
            "type": _feature_type_to_correction_type(feat.get("feature_type", "")),
            "corrected_box": corrected_box,
            "anchor_point": anchor_point,
            "view_name": feat.get("view_name"),
        })
    return results


# ── Operation 1: Text Box Refinement ──────────────────────────────────────

def refine_text_box(gray_image, box_2d: List[float],
                    padding: int = TEXT_CROP_PADDING) -> Tuple[int, int, int, int]:
    """
    Crop the region around the AI bounding box, threshold to binary,
    find text contours, and compute a tighter bounding box.

    Returns (x1, y1, x2, y2) refined bounding box, or original if fails.
    """
    import cv2
    import numpy as np

    x1, y1, x2, y2 = _box2d_to_xyxy(box_2d)
    img_h, img_w = gray_image.shape

    # Expand crop region with padding
    crop_x1 = max(0, x1 - padding)
    crop_y1 = max(0, y1 - padding)
    crop_x2 = min(img_w, x2 + padding)
    crop_y2 = min(img_h, y2 + padding)

    crop = gray_image[crop_y1:crop_y2, crop_x1:crop_x2]
    if crop.size == 0:
        return x1, y1, x2, y2

    # Adaptive threshold for engineering drawings (varying line weights)
    binary = cv2.adaptiveThreshold(
        crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=11, C=2
    )

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return x1, y1, x2, y2

    # Filter contours: keep text-like (area > 10, reasonable aspect ratio)
    text_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 10:
            continue
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bh > 0 and bw / bh > 0.05:  # not just a thin line
            text_contours.append(cnt)

    if not text_contours:
        return x1, y1, x2, y2

    # Union bounding box of all text contours
    all_points = np.concatenate(text_contours)
    rx, ry, rw, rh = cv2.boundingRect(all_points)

    # Convert crop-local to absolute coordinates
    abs_x1 = crop_x1 + rx
    abs_y1 = crop_y1 + ry
    abs_x2 = abs_x1 + rw
    abs_y2 = abs_y1 + rh

    return abs_x1, abs_y1, abs_x2, abs_y2


# ── Operation 2: Snap-to-Text Correction ──────────────────────────────────

def snap_to_nearest_text(gray_image,
                         box_x1: int, box_y1: int,
                         box_x2: int, box_y2: int,
                         search_radius: int = SNAP_SEARCH_RADIUS
                         ) -> Tuple[int, int, int, int]:
    """
    Search for text-like contour clusters near the current box and snap
    to the nearest one if the AI coordinate was slightly off.

    Returns (x1, y1, x2, y2) snapped box, or original if no better found.
    """
    import cv2
    import numpy as np

    img_h, img_w = gray_image.shape

    # Expand search region
    sx1 = max(0, box_x1 - search_radius)
    sy1 = max(0, box_y1 - search_radius)
    sx2 = min(img_w, box_x2 + search_radius)
    sy2 = min(img_h, box_y2 + search_radius)

    crop = gray_image[sy1:sy2, sx1:sx2]
    if crop.size == 0:
        return box_x1, box_y1, box_x2, box_y2

    binary = cv2.adaptiveThreshold(
        crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=11, C=2
    )

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return box_x1, box_y1, box_x2, box_y2

    # Build bounding rects for contours with reasonable size
    rects = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 8:
            continue
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw > 3 and bh > 3:
            rects.append((bx, by, bx + bw, by + bh))

    if not rects:
        return box_x1, box_y1, box_x2, box_y2

    # Simple clustering: merge overlapping or nearby rects
    clusters = _cluster_rects(rects, merge_distance=8)

    if not clusters:
        return box_x1, box_y1, box_x2, box_y2

    # Find cluster with center closest to current box center
    box_cx = (box_x1 + box_x2) / 2 - sx1  # local coords
    box_cy = (box_y1 + box_y2) / 2 - sy1

    best_cluster = None
    best_dist = float("inf")

    for cl_x1, cl_y1, cl_x2, cl_y2 in clusters:
        cl_cx = (cl_x1 + cl_x2) / 2
        cl_cy = (cl_y1 + cl_y2) / 2
        cl_w = cl_x2 - cl_x1
        cl_h = cl_y2 - cl_y1

        # Text-like filter: width > 5, not extremely thin
        if cl_w < 5 or cl_h < 3:
            continue

        dist = _euclidean_distance((box_cx, box_cy), (cl_cx, cl_cy))
        if dist < best_dist:
            best_dist = dist
            best_cluster = (cl_x1, cl_y1, cl_x2, cl_y2)

    if best_cluster and best_dist < search_radius:
        # Convert to absolute coordinates
        return (
            sx1 + best_cluster[0],
            sy1 + best_cluster[1],
            sx1 + best_cluster[2],
            sy1 + best_cluster[3],
        )

    return box_x1, box_y1, box_x2, box_y2


def _cluster_rects(rects: List[Tuple[int, int, int, int]],
                   merge_distance: int = 8
                   ) -> List[Tuple[int, int, int, int]]:
    """Merge overlapping or nearby rectangles into clusters."""
    if not rects:
        return []

    # Sort by x1 for efficient merging
    rects = sorted(rects, key=lambda r: r[0])
    clusters = [list(rects[0])]

    for rx1, ry1, rx2, ry2 in rects[1:]:
        merged = False
        for cl in clusters:
            # Check if rect overlaps or is within merge_distance of cluster
            if (rx1 <= cl[2] + merge_distance and rx2 >= cl[0] - merge_distance and
                    ry1 <= cl[3] + merge_distance and ry2 >= cl[1] - merge_distance):
                # Expand cluster to include this rect
                cl[0] = min(cl[0], rx1)
                cl[1] = min(cl[1], ry1)
                cl[2] = max(cl[2], rx2)
                cl[3] = max(cl[3], ry2)
                merged = True
                break
        if not merged:
            clusters.append([rx1, ry1, rx2, ry2])

    return [tuple(c) for c in clusters]


# ── Operation 3: Leader Line Detection ────────────────────────────────────

def detect_leader_lines(gray_image,
                        box_x1: int, box_y1: int,
                        box_x2: int, box_y2: int,
                        search_margin: int = 60
                        ) -> Optional[Tuple[int, int]]:
    """
    Use Canny + HoughLinesP to detect leader lines near the dimension text.
    Returns the far endpoint of the leader line (pointing to geometry), or None.
    """
    import cv2
    import numpy as np

    img_h, img_w = gray_image.shape

    # Search region around text box
    rx1 = max(0, box_x1 - search_margin)
    ry1 = max(0, box_y1 - search_margin)
    rx2 = min(img_w, box_x2 + search_margin)
    ry2 = min(img_h, box_y2 + search_margin)

    crop = gray_image[ry1:ry2, rx1:rx2]
    if crop.size == 0:
        return None

    # Edge detection
    edges = cv2.Canny(crop, CANNY_LOW, CANNY_HIGH, apertureSize=3)

    # Detect lines
    lines = cv2.HoughLinesP(
        edges, 1, math.pi / 180,
        threshold=LEADER_LINE_THRESHOLD,
        minLineLength=LEADER_MIN_LINE_LENGTH,
        maxLineGap=LEADER_MAX_LINE_GAP,
    )

    if lines is None or len(lines) == 0:
        return None

    # Text box center in crop-local coordinates
    text_cx = (box_x1 + box_x2) / 2 - rx1
    text_cy = (box_y1 + box_y2) / 2 - ry1

    # Text box edges in crop-local coordinates
    local_bx1 = box_x1 - rx1
    local_by1 = box_y1 - ry1
    local_bx2 = box_x2 - rx1
    local_by2 = box_y2 - ry1

    best_line = None
    best_length = 0

    for line in lines:
        lx1, ly1, lx2, ly2 = line[0]

        # Compute distances of both endpoints to text box edges
        dist1_to_box = _point_to_box_distance(
            lx1, ly1, local_bx1, local_by1, local_bx2, local_by2
        )
        dist2_to_box = _point_to_box_distance(
            lx2, ly2, local_bx1, local_by1, local_bx2, local_by2
        )

        # One endpoint should be close to text box (< 15px)
        # But BOTH near means it's a box edge, not a leader line
        near_threshold = 15
        if dist1_to_box < near_threshold and dist2_to_box < near_threshold:
            continue  # Both endpoints near text — it's a box edge, skip
        elif dist1_to_box < near_threshold:
            far_x, far_y = lx2, ly2
        elif dist2_to_box < near_threshold:
            far_x, far_y = lx1, ly1
        else:
            continue  # Neither endpoint near text — not a leader line

        line_length = math.sqrt((lx2 - lx1) ** 2 + (ly2 - ly1) ** 2)
        if line_length > best_length:
            best_length = line_length
            best_line = (rx1 + far_x, ry1 + far_y)  # Convert to absolute

    return best_line


def _point_to_box_distance(px: int, py: int,
                           bx1: int, by1: int,
                           bx2: int, by2: int) -> float:
    """Compute shortest distance from point (px, py) to rectangle edges."""
    dx = max(bx1 - px, 0, px - bx2)
    dy = max(by1 - py, 0, py - by2)
    return math.sqrt(dx ** 2 + dy ** 2)


# ── Operation 4: Geometry Detection ───────────────────────────────────────

def detect_associated_geometry(gray_image,
                               box_x1: int, box_y1: int,
                               box_x2: int, box_y2: int,
                               feature_type: str,
                               specification: str,
                               search_margin: int = 100
                               ) -> Optional[Tuple[int, int]]:
    """
    For diameter features (Ø): detect circles using HoughCircles.
    For length features: detect parallel lines.
    Returns geometry center (x, y) or None.
    """
    import cv2
    import numpy as np

    is_diameter = feature_type in ("OD", "ID") or "Ø" in specification or "ø" in specification
    is_length = feature_type == "LENGTH"

    if not is_diameter and not is_length:
        return None

    img_h, img_w = gray_image.shape
    rx1 = max(0, box_x1 - search_margin)
    ry1 = max(0, box_y1 - search_margin)
    rx2 = min(img_w, box_x2 + search_margin)
    ry2 = min(img_h, box_y2 + search_margin)

    crop = gray_image[ry1:ry2, rx1:rx2]
    if crop.size == 0:
        return None

    if is_diameter:
        return _detect_circles(crop, rx1, ry1, box_x1, box_y1, box_x2, box_y2)

    if is_length:
        return _detect_parallel_lines(crop, rx1, ry1, box_x1, box_y1, box_x2, box_y2)

    return None


def _detect_circles(crop, offset_x: int, offset_y: int,
                    box_x1: int, box_y1: int,
                    box_x2: int, box_y2: int
                    ) -> Optional[Tuple[int, int]]:
    """Detect circles using HoughCircles and return nearest center."""
    import cv2
    import numpy as np

    blurred = cv2.GaussianBlur(crop, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT,
        dp=HOUGH_CIRCLES_DP,
        minDist=HOUGH_CIRCLES_MIN_DIST,
        param1=HOUGH_CIRCLES_PARAM1,
        param2=HOUGH_CIRCLES_PARAM2,
        minRadius=HOUGH_CIRCLES_MIN_RADIUS,
        maxRadius=HOUGH_CIRCLES_MAX_RADIUS,
    )

    if circles is None:
        return None

    # Convert to absolute coordinates and find nearest to text box center
    box_cx = (box_x1 + box_x2) / 2
    box_cy = (box_y1 + box_y2) / 2

    best_center = None
    best_dist = float("inf")

    for circle in circles[0]:
        cx, cy, r = circle
        abs_cx = int(offset_x + cx)
        abs_cy = int(offset_y + cy)
        dist = _euclidean_distance((abs_cx, abs_cy), (box_cx, box_cy))
        if dist < best_dist:
            best_dist = dist
            best_center = (abs_cx, abs_cy)

    return best_center


def _detect_parallel_lines(crop, offset_x: int, offset_y: int,
                           box_x1: int, box_y1: int,
                           box_x2: int, box_y2: int
                           ) -> Optional[Tuple[int, int]]:
    """Detect parallel line pairs and return midpoint between them."""
    import cv2
    import numpy as np

    edges = cv2.Canny(crop, CANNY_LOW, CANNY_HIGH, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, 1, math.pi / 180,
        threshold=50, minLineLength=30, maxLineGap=15,
    )

    if lines is None or len(lines) < 2:
        return None

    # Find pairs of approximately parallel lines (angle diff < 5 degrees)
    line_data = []
    for line in lines:
        lx1, ly1, lx2, ly2 = line[0]
        angle = math.degrees(math.atan2(ly2 - ly1, lx2 - lx1)) % 180
        length = math.sqrt((lx2 - lx1) ** 2 + (ly2 - ly1) ** 2)
        mid_x = (lx1 + lx2) / 2
        mid_y = (ly1 + ly2) / 2
        line_data.append((angle, length, mid_x, mid_y))

    # Sort by length (longest first) for better parallel pair detection
    line_data.sort(key=lambda d: -d[1])

    for i in range(len(line_data)):
        for j in range(i + 1, len(line_data)):
            angle_diff = abs(line_data[i][0] - line_data[j][0])
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            if angle_diff < 5:  # Nearly parallel
                separation = _euclidean_distance(
                    (line_data[i][2], line_data[i][3]),
                    (line_data[j][2], line_data[j][3]),
                )
                if separation > 10:  # Meaningfully separated
                    mid_x = (line_data[i][2] + line_data[j][2]) / 2
                    mid_y = (line_data[i][3] + line_data[j][3]) / 2
                    return (int(offset_x + mid_x), int(offset_y + mid_y))

    return None


# ── Operation 5: Balloon Placement ────────────────────────────────────────

def compute_anchor_and_placement(
    box_x1: int, box_y1: int, box_x2: int, box_y2: int,
    leader_point: Optional[Tuple[int, int]],
    geometry_center: Optional[Tuple[int, int]],
    img_w: int, img_h: int,
    offset: int = BALLOON_OFFSET_PX
) -> Tuple[int, int]:
    """
    Compute anchor point for balloon placement.
    Priority: leader line endpoint > geometry center > text box edge offset.
    """
    margin = BALLOON_DIAMETER // 2

    # Priority 1: Leader line endpoint
    if leader_point is not None:
        ax, ay = leader_point
        ax = max(margin, min(ax, img_w - margin))
        ay = max(margin, min(ay, img_h - margin))
        return (ax, ay)

    # Priority 2: Point between text and geometry
    if geometry_center is not None:
        box_cx = (box_x1 + box_x2) / 2
        box_cy = (box_y1 + box_y2) / 2
        gx, gy = geometry_center

        # Anchor halfway between text edge and geometry center
        ax = int((box_cx + gx) / 2)
        ay = int((box_cy + gy) / 2)

        # Ensure offset from text box
        if box_x1 <= ax <= box_x2 and box_y1 <= ay <= box_y2:
            # Still inside text box, push toward geometry
            dx = gx - box_cx
            dy = gy - box_cy
            dist = max(1, math.sqrt(dx * dx + dy * dy))
            ax = int(box_cx + (dx / dist) * offset)
            ay = int(box_cy + (dy / dist) * offset)

        ax = max(margin, min(ax, img_w - margin))
        ay = max(margin, min(ay, img_h - margin))
        return (ax, ay)

    # Priority 3: Text box edge with most free space
    left_space = box_x1
    right_space = img_w - box_x2
    top_space = box_y1
    bottom_space = img_h - box_y2

    box_cy = (box_y1 + box_y2) // 2
    box_cx = (box_x1 + box_x2) // 2

    max_space = max(left_space, right_space, top_space, bottom_space)

    if max_space == left_space:
        ax = box_x1 - offset
        ay = box_cy
    elif max_space == right_space:
        ax = box_x2 + offset
        ay = box_cy
    elif max_space == top_space:
        ax = box_cx
        ay = box_y1 - offset
    else:
        ax = box_cx
        ay = box_y2 + offset

    ax = max(margin, min(ax, img_w - margin))
    ay = max(margin, min(ay, img_h - margin))
    return (ax, ay)


# ── Operation 6: Collision Avoidance ──────────────────────────────────────

def resolve_collisions(
    anchor: Tuple[int, int],
    placed_anchors: List[Tuple[int, int]],
    img_w: int, img_h: int,
    min_distance: int = COLLISION_DISTANCE_THRESHOLD,
    shift_px: int = COLLISION_SHIFT_PX
) -> Tuple[int, int]:
    """
    If anchor overlaps existing balloons, shift until no collision.
    Tries 4 directions with escalating distance.
    """
    margin = BALLOON_DIAMETER // 2

    def has_collision(pt: Tuple[int, int]) -> bool:
        for placed in placed_anchors:
            if _euclidean_distance(pt, placed) < min_distance:
                return True
        return False

    if not has_collision(anchor):
        return anchor

    # Try escalating shifts in 4 directions
    for multiplier in range(1, 4):
        shift = shift_px * multiplier
        for dx, dy in SHIFT_DIRECTIONS:
            candidate = (
                max(margin, min(anchor[0] + dx * shift, img_w - margin)),
                max(margin, min(anchor[1] + dy * shift, img_h - margin)),
            )
            if not has_collision(candidate):
                return candidate

    # All candidates collide — pick the one with greatest min distance
    best = anchor
    best_min_dist = 0

    for multiplier in range(1, 4):
        shift = shift_px * multiplier
        for dx, dy in SHIFT_DIRECTIONS:
            candidate = (
                max(margin, min(anchor[0] + dx * shift, img_w - margin)),
                max(margin, min(anchor[1] + dy * shift, img_h - margin)),
            )
            min_d = min(
                (_euclidean_distance(candidate, p) for p in placed_anchors),
                default=float("inf"),
            )
            if min_d > best_min_dist:
                best_min_dist = min_d
                best = candidate

    return best


# ── Main Orchestrator ─────────────────────────────────────────────────────

def refine_feature_coordinates(
    image_path: str,
    features: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Main entry point for the geometry correction layer.
    Runs the 6-step correction pipeline on all features.

    Args:
        image_path: path to the PNG drawing image
        features: list of feature dicts from vision extraction,
                  each containing box_2d = [ymin, xmin, ymax, xmax]

    Returns:
        List of corrected feature dicts with:
        - balloon_no: int
        - spec: str
        - type: str
        - corrected_box: [x1, y1, x2, y2]
        - anchor_point: [x, y]

    Also mutates the original features in-place, updating box_2d
    with the corrected coordinates (for downstream compatibility
    with generate_ballooned_image).
    """
    try:
        import cv2
    except ImportError:
        print("[GeometryCorrection] OpenCV not installed, skipping correction")
        return _passthrough(features)

    img_color = cv2.imread(image_path)
    if img_color is None:
        print(f"[GeometryCorrection] Could not load image: {image_path}")
        return _passthrough(features)

    gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
    img_h, img_w = gray.shape

    print(f"[GeometryCorrection] Processing {len(features)} features on {img_w}x{img_h} image")

    corrected_results = []
    placed_anchors = []

    for feat in features:
        balloon_no = feat.get("balloon_no")
        spec = feat.get("specification", "")
        feature_type = feat.get("feature_type", "")
        box_2d = feat.get("box_2d")

        # Skip features with no/invalid box_2d
        if not box_2d or not isinstance(box_2d, list) or len(box_2d) != 4:
            corrected_results.append({
                "balloon_no": balloon_no,
                "spec": spec,
                "type": _feature_type_to_correction_type(feature_type),
                "corrected_box": None,
                "anchor_point": None,
            })
            continue

        # Convert [ymin, xmin, ymax, xmax] -> (x1, y1, x2, y2)
        x1, y1, x2, y2 = _box2d_to_xyxy(box_2d)
        x1, y1, x2, y2 = _clamp_box(x1, y1, x2, y2, img_w, img_h)

        # ── Step 1: Text box refinement ──
        try:
            rx1, ry1, rx2, ry2 = refine_text_box(gray, box_2d)
            rx1, ry1, rx2, ry2 = _clamp_box(rx1, ry1, rx2, ry2, img_w, img_h)
        except Exception as e:
            print(f"[GeometryCorrection] Text refinement failed for #{balloon_no}: {e}")
            rx1, ry1, rx2, ry2 = x1, y1, x2, y2

        # ── Step 2: Snap to nearest text cluster ──
        try:
            sx1, sy1, sx2, sy2 = snap_to_nearest_text(gray, rx1, ry1, rx2, ry2)
            sx1, sy1, sx2, sy2 = _clamp_box(sx1, sy1, sx2, sy2, img_w, img_h)
        except Exception as e:
            print(f"[GeometryCorrection] Snap-to-text failed for #{balloon_no}: {e}")
            sx1, sy1, sx2, sy2 = rx1, ry1, rx2, ry2

        # ── Step 3: Leader line detection ──
        leader_point = None
        try:
            leader_point = detect_leader_lines(gray, sx1, sy1, sx2, sy2)
        except Exception as e:
            print(f"[GeometryCorrection] Leader detection failed for #{balloon_no}: {e}")

        # ── Step 4: Geometry detection ──
        geometry_center = None
        try:
            geometry_center = detect_associated_geometry(
                gray, sx1, sy1, sx2, sy2, feature_type, spec
            )
        except Exception as e:
            print(f"[GeometryCorrection] Geometry detection failed for #{balloon_no}: {e}")

        # ── Step 5: Balloon placement ──
        try:
            anchor = compute_anchor_and_placement(
                sx1, sy1, sx2, sy2,
                leader_point, geometry_center,
                img_w, img_h,
            )
        except Exception as e:
            print(f"[GeometryCorrection] Placement failed for #{balloon_no}: {e}")
            anchor = ((sx1 + sx2) // 2 - BALLOON_OFFSET_PX, (sy1 + sy2) // 2)

        # ── Step 6: Collision avoidance ──
        try:
            anchor = resolve_collisions(anchor, placed_anchors, img_w, img_h)
        except Exception as e:
            print(f"[GeometryCorrection] Collision resolve failed for #{balloon_no}: {e}")

        placed_anchors.append(anchor)

        # Update original feature's box_2d in-place for downstream compatibility
        feat["box_2d"] = _xyxy_to_box2d(sx1, sy1, sx2, sy2)
        feat["anchor_point"] = [int(anchor[0]), int(anchor[1])]
        
        corrected_results.append({
            "balloon_no": int(balloon_no) if balloon_no is not None else None,
            "spec": spec,
            "type": _feature_type_to_correction_type(feature_type),
            "corrected_box": [int(sx1), int(sy1), int(sx2), int(sy2)],
            "anchor_point": [int(anchor[0]), int(anchor[1])],
            "view_name": feat.get("view_name"),
        })

        print(f"  #{balloon_no} {spec}: box=[{sx1},{sy1},{sx2},{sy2}] "
              f"anchor={list(anchor)} "
              f"leader={'yes' if leader_point else 'no'} "
              f"geom={'yes' if geometry_center else 'no'}")

    print(f"[GeometryCorrection] Refined {len(corrected_results)} features.")
    return corrected_results
