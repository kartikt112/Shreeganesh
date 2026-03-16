import cv2
import numpy as np
import math
from typing import List, Dict, Any, Tuple

# Minimum distance allowed between two balloons
COLLISION_DISTANCE = 40
# Space out balloons uniformly in rows/columns
BALLOON_SPACING = 100
# Margin to keep away from the part bounding box
PART_MARGIN = 120
# Offsets to try when resolving collisions iteratively
COLLISION_OFFSETS = [(40, 0), (80, 0), (0, 40), (0, 80), (-40, 0), (0, -40), (40, 40), (-40, -40)]

def detect_part_bbox(image_path: str) -> Tuple[int, int, int, int]:
    """
    Detect the bounding box of the main part geometry using Canny edge detection
    and contour finding.

    Returns:
        (xmin, ymin, xmax, ymax) representing the part geometry bounding box.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
        
    img_h, img_w = img.shape
    
    # Simple denoise
    blurred = cv2.GaussianBlur(img, (5, 5), 0)
    
    # Edge detection
    edges = cv2.Canny(blurred, 30, 120)
    
    # Find contours from edges
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        # Fallback if nothing detected: center 50% of the image
        return (img_w // 4, img_h // 4, 3 * img_w // 4, 3 * img_h // 4)
        
    # Find the largest bounding box that encapsulates the major contours
    # Filter out very small noise contours
    valid_contours = [c for c in contours if cv2.contourArea(c) > 100 or len(c) > 50]
    
    if not valid_contours:
        valid_contours = contours # fallback to all if filtering removed everything
        
    # Compute the union bounding box of all valid contours
    all_points = np.concatenate(valid_contours)
    x, y, w, h = cv2.boundingRect(all_points)
    
    return (x, y, x + w, y + h)

def assign_layout_zone(anchor_x: int, anchor_y: int, part_bbox: Tuple[int, int, int, int], img_w: int, img_h: int) -> str:
    """
    Assign a layout zone (TOP, BOTTOM, LEFT, RIGHT) based on the anchor point's
    relative position to the part bounding box and the available space.
    """
    xmin, ymin, xmax, ymax = part_bbox
    
    # Calculate distances to each edge of the part bounding box
    dist_left = abs(anchor_x - xmin)
    dist_right = abs(anchor_x - xmax)
    dist_top = abs(anchor_y - ymin)
    dist_bottom = abs(anchor_y - ymax)
    
    # Priority: Which side of the bounding box is the anchor closest to?
    # but also consider if it's strictly outside the box.
    
    if anchor_y < ymin:
        return "TOP"
    elif anchor_y > ymax:
        return "BOTTOM"
    elif anchor_x < xmin:
        return "LEFT"
    elif anchor_x > xmax:
        return "RIGHT"
        
    # If the anchor is inside the bounding box, map it to the nearest edge
    min_dist = min(dist_left, dist_right, dist_top, dist_bottom)
    
    if min_dist == dist_top:
        return "TOP"
    elif min_dist == dist_bottom:
        return "BOTTOM"
    elif min_dist == dist_left:
        return "LEFT"
    else:
        return "RIGHT"

def resolve_balloon_collisions(features: List[Dict[str, Any]], img_w: int, img_h: int):
    """
    Iteratively resolve collisions between balloon positions.
    Modifies features in-place.
    """
    placed_positions = []
    
    for feat in features:
        bx, by = feat.get("balloon_position", (0, 0))
        
        # Check for collisions with already placed balloons
        collision = True
        while collision:
            collision = False
            for px, py in placed_positions:
                dist = math.sqrt((bx - px)**2 + (by - py)**2)
                if dist < COLLISION_DISTANCE:
                    collision = True
                    break
                    
            if collision:
                # Try offsets until we find a clear spot
                resolved = False
                for dx, dy in COLLISION_OFFSETS:
                    candidate_bx = max(20, min(bx + dx, img_w - 20))
                    candidate_by = max(20, min(by + dy, img_h - 20))
                    
                    # Check if this offset works against ALL placed so far
                    candidate_collision = False
                    for px, py in placed_positions:
                        if math.sqrt((candidate_bx - px)**2 + (candidate_by - py)**2) < COLLISION_DISTANCE:
                            candidate_collision = True
                            break
                            
                    if not candidate_collision:
                        bx, by = candidate_bx, candidate_by
                        resolved = True
                        break
                
                if not resolved:
                    # If offsets didn't work, just force a shift to the right/down
                    bx = min(bx + COLLISION_DISTANCE, img_w - 20)
                    by = min(by + COLLISION_DISTANCE, img_h - 20)
                    # Loop will re-evaluate this new position
                    
        feat["balloon_position"] = [int(bx), int(by)]
        placed_positions.append((bx, by))

def generate_zone_positions(features: List[Dict[str, Any]], zone: str, part_bbox: Tuple[int, int, int, int], img_w: int, img_h: int):
    """
    Generate initial structured positions for balloons within a specific zone.
    Aligns them in rows/columns based on the zone.
    Modifies features in-place to add 'balloon_position'.
    """
    zone_features = [f for f in features if f.get("layout_zone") == zone]
    if not zone_features:
        return
        
    xmin, ymin, xmax, ymax = part_bbox
    
    if zone == "TOP":
        # Sort left to right by anchor_x
        zone_features.sort(key=lambda f: f["anchor_point"][0] if f.get("anchor_point") else 0)
        base_y = max(40, ymin - PART_MARGIN)
        start_x = max(40, xmin)
        for i, feat in enumerate(zone_features):
            feat["balloon_position"] = [start_x + i * BALLOON_SPACING, base_y]
            
    elif zone == "BOTTOM":
        # Sort left to right by anchor_x
        zone_features.sort(key=lambda f: f["anchor_point"][0] if f.get("anchor_point") else 0)
        base_y = min(img_h - 40, ymax + PART_MARGIN)
        start_x = max(40, xmin)
        for i, feat in enumerate(zone_features):
            feat["balloon_position"] = [start_x + i * BALLOON_SPACING, base_y]
            
    elif zone == "LEFT":
        # Sort top to bottom by anchor_y
        zone_features.sort(key=lambda f: f["anchor_point"][1] if f.get("anchor_point") else 0)
        base_x = max(40, xmin - PART_MARGIN)
        start_y = max(40, ymin)
        for i, feat in enumerate(zone_features):
            feat["balloon_position"] = [base_x, start_y + i * BALLOON_SPACING]
            
    elif zone == "RIGHT":
        # Sort top to bottom by anchor_y
        zone_features.sort(key=lambda f: f["anchor_point"][1] if f.get("anchor_point") else 0)
        base_x = min(img_w - 40, xmax + PART_MARGIN)
        start_y = max(40, ymin)
        for i, feat in enumerate(zone_features):
            feat["balloon_position"] = [base_x, start_y + i * BALLOON_SPACING]


def compute_balloon_layout(image_path: str, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Main layout engine entry point.
    Intelligently positions balloons around the drawing to avoid overlap and crossing.
    
    Args:
        image_path: Path to the drawing image.
        features: List of feature dictionaries containing 'corrected_box' and 'anchor_point'.
        
    Returns:
        List of features with updated 'balloon_position'.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"[BalloonLayoutEngine] Error reading image from {image_path}, falling back to anchor points.")
            # Fallback
            for feat in features:
                if "anchor_point" in feat and feat["anchor_point"]:
                    feat["balloon_position"] = feat["anchor_point"]
            return features
            
        img_h, img_w = img.shape[:2]
    except Exception as e:
        print(f"[BalloonLayoutEngine] OpenCV Error: {e}")
        # Fallback
        for feat in features:
            if "anchor_point" in feat and feat["anchor_point"]:
                feat["balloon_position"] = feat["anchor_point"]
        return features

    # 1. Detect part bounding box
    part_bbox = detect_part_bbox(image_path)
    
    # 2. Assign features to zones
    for feat in features:
        anchor_pt = feat.get("anchor_point")
        if not anchor_pt or len(anchor_pt) != 2:
            # If no anchor, try to derive one from bounding box
            box = feat.get("corrected_box") or feat.get("box_2d")
            if box and len(box) == 4:
                ymin, xmin, ymax, xmax = box
                anchor_pt = [int((xmin + xmax) / 2), int((ymin + ymax) / 2)]
                feat["anchor_point"] = anchor_pt
            else:
                # Absolute fallback
                feat["layout_zone"] = "RIGHT" 
                feat["balloon_position"] = [img_w - 50, 50]
                continue
                
        feat["layout_zone"] = assign_layout_zone(anchor_pt[0], anchor_pt[1], part_bbox, img_w, img_h)

    # 3. Generate structured balloon positions per zone
    for zone in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
        generate_zone_positions(features, zone, part_bbox, img_w, img_h)
        
    # 4. Global collision resolution (in case zone layouts overlap at corners)
    resolve_balloon_collisions(features, img_w, img_h)
    
    print(f"[BalloonLayoutEngine] Placed {len(features)} balloons. Part BBox: {part_bbox}")
    return features
