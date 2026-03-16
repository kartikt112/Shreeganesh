import cv2
import numpy as np
import math
from typing import List, Dict, Any, Tuple

def _box2d_to_xyxy(box: List[float]) -> Tuple[int, int, int, int]:
    return int(box[1]), int(box[0]), int(box[3]), int(box[2])

def _distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def refine_geometry(image_path: str, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Step 3: Geometry Correction
    Refines bounding boxes utilizing OpenCV, detects leader lines, and assigns precision anchors.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
        
    img_h, img_w = img.shape
    
    # Pre-compute inverted threshold for contour detection
    _, binary = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY_INV)

    refined_features = []
    
    for feat in features:
        box_pct = feat.get("bounding_box_pct")
        if not box_pct or len(box_pct) != 4:
            refined_features.append(feat)
            continue
            
        # Convert percent to absolute pixels
        ymin = (box_pct[0] / 1000.0) * img_h
        xmin = (box_pct[1] / 1000.0) * img_w
        ymax = (box_pct[2] / 1000.0) * img_h
        xmax = (box_pct[3] / 1000.0) * img_w
        
        feat["bbox"] = [ymin, xmin, ymax, xmax]
        
        x1, y1, x2, y2 = _box2d_to_xyxy(feat["bbox"])
        
        # 1. Crop image region around bbox
        pad = 30
        crop_y1 = max(0, y1 - pad)
        crop_x1 = max(0, x1 - pad)
        crop_y2 = min(img_h, y2 + pad)
        crop_x2 = min(img_w, x2 + pad)
        
        roi = binary[crop_y1:crop_y2, crop_x1:crop_x2]
        
        if roi.size > 0:
            # 2. Detect contours to refine bounding box
            contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                all_pts = np.concatenate(contours)
                rx, ry, rw, rh = cv2.boundingRect(all_pts)
                
                # Update bbox mapping back to global coords
                x1 = crop_x1 + rx
                y1 = crop_y1 + ry
                x2 = x1 + rw
                y2 = y1 + rh
                feat["bbox"] = [y1, x1, y2, x2]
                
            # 3. Detect leader lines using Hough transform
            lines = cv2.HoughLinesP(roi, 1, np.pi/180, threshold=30, minLineLength=20, maxLineGap=5)
            best_anchor = None
            if lines is not None:
                # Find line endpoint furthest from text center
                text_cx = (x1 + x2) / 2
                text_cy = (y1 + y2) / 2
                max_dist = 0
                
                for line in lines:
                    lx1, ly1, lx2, ly2 = line[0]
                    # Map to global
                    glx1, gly1 = crop_x1 + lx1, crop_y1 + ly1
                    glx2, gly2 = crop_x1 + lx2, crop_y1 + ly2
                    
                    d1 = _distance((text_cx, text_cy), (glx1, gly1))
                    d2 = _distance((text_cx, text_cy), (glx2, gly2))
                    
                    if d1 > max_dist:
                        max_dist = d1
                        best_anchor = [glx1, gly1]
                    if d2 > max_dist:
                        max_dist = d2
                        best_anchor = [glx2, gly2]
                        
            if best_anchor:
                feat["anchor"] = [int(best_anchor[0]), int(best_anchor[1])]
            else:
                # Estimate anchor point if no explicit leader found (use bbox edge)
                feat["anchor"] = [int(x2) + 20, int((y1 + y2)/2)]
        else:
            feat["anchor"] = [int(x2) + 20, int((y1 + y2)/2)]
            
        refined_features.append(feat)
        
    return refined_features
