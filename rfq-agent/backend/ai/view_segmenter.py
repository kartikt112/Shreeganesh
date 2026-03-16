import cv2
import numpy as np
from typing import List, Dict, Any, Tuple

def segment_views(image_path: str) -> List[Dict[str, int]]:
    """
    Step 5: View Segmentation
    Detect separate engineering drawing views using connected-component analysis.
    Filters out the title block and general notes.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
        
    img_h, img_w = img.shape
    
    # 1. Threshold
    _, binary = cv2.threshold(img, 240, 255, cv2.THRESH_BINARY_INV)
    
    # Dilate heavily to merge parts of the same view
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (100, 100))
    dilated = cv2.dilate(binary, kernel, iterations=2)
    
    # 2. Extract connected regions
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    
    views = []
    view_id = 1
    
    for i in range(1, num_labels): # skip background (0)
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        
        # 4. Filter logic
        # Skip tiny components (noise)
        if area < (img_w * img_h) * 0.01:
            continue
            
        # Filter Title Block (Bottom-Right)
        is_title_block = (x + w > img_w * 0.7) and (y + h > img_h * 0.7)
        
        # Filter Notes Block (often top-right or bottom-left but long and texty)
        is_note_block = w > (img_w * 0.4) and h < (img_h * 0.2)
        
        if not is_title_block and not is_note_block:
            views.append({
                "view_id": view_id,
                "bbox": [x, y, x + w, y + h] # xmin, ymin, xmax, ymax
            })
            view_id += 1
            
    # Fallback if no views found
    if not views:
        views.append({
            "view_id": 1,
            "bbox": [50, 50, img_w - 50, img_h - 50]
        })
        
    # Sort views (top-to-bottom, left-to-right)
    views.sort(key=lambda v: (v["bbox"][1] // 200, v["bbox"][0]))
    
    for i, v in enumerate(views):
        v["view_id"] = i + 1
        
    return views
