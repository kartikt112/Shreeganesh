import cv2
import numpy as np
from typing import List, Dict, Any, Tuple

def create_occupancy_bitmap(image_path: str, features: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, int, int, Any]:
    """
    Step 8: Occupancy Bitmap (Distance Transform)
    Builds a free-space continuous distance map from the drawing image.
    This replaces the boolean threshold to allow fine-tuning balloons into perfectly cleared margin lanes.
    """
    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"Could not read image: {image_path}")
        
    img_h, img_w = gray.shape
    
    # Binary: white pixels (>200) = free, dark = occupied
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    
    # Title block detection: bottom-right region (approx 60% down, 45% right)
    tb_y = int(img_h * 0.60)
    tb_x = int(img_w * 0.45)
    title_block_rect = None
    
    region = binary[tb_y:, tb_x:]
    if region.size > 0:
        ink_ratio = 1.0 - (float(np.sum(region > 200)) / region.size)
        if ink_ratio > 0.05:
            title_block_rect = (tb_x, tb_y, img_w, img_h)
            binary[tb_y:, tb_x:] = 0  # mark title block as occupied
            
    # Dilate occupied areas by safety margin to push distance map further away
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    occupied = cv2.dilate(255 - binary, kernel)
    
    # Feature text bounding boxes should be avoided
    for f in features:
        bbox = f.get("bbox")
        if bbox and len(bbox) == 4:
            y1, x1, y2, x2 = map(int, bbox)
            occupied[max(0, y1-10):min(img_h, y2+10), max(0, x1-10):min(img_w, x2+10)] = 255
    
    free_mask = 255 - occupied
    
    # Distance transform: each free pixel -> distance to nearest ink
    dist_map = cv2.distanceTransform(free_mask, cv2.DIST_L2, 5)
    
    return dist_map, occupied, img_h, img_w, title_block_rect

def update_occupancy(occupancy: np.ndarray, cx: int, cy: int, radius: int):
    """Mark a placed balloon footprint on the grid to prevent overlaps."""
    # (Optional interface for backward compatibility if needed, though Margin Lane uses its own list)
    h, w = occupancy.shape
    y_idx, x_idx = np.ogrid[-radius-5:radius+6, -radius-5:radius+6]
    mask = x_idx**2 + y_idx**2 <= (radius+5)**2
    
    y1 = max(0, cy - radius - 5)
    y2 = min(h, cy + radius + 6)
    x1 = max(0, cx - radius - 5)
    x2 = min(w, cx + radius + 6)
    
    mask_y1 = radius + 5 - (cy - y1)
    mask_y2 = radius + 5 + (y2 - cy)
    mask_x1 = radius + 5 - (cx - x1)
    mask_x2 = radius + 5 + (x2 - cx)
    
    if len(occupancy.shape) == 2:
        occupancy[y1:y2, x1:x2][mask[mask_y1:mask_y2, mask_x1:mask_x2]] = 1
