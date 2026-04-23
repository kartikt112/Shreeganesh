import cv2
import numpy as np
import math
import json
import os

def _extract_balloons_from_gemini_image(
    gemini_image_path: str,
    json_coords: list,
    expected_balloons: list,
    resized_input_size=(2048, 1448),
):
    print(f"Loading image: {gemini_image_path}")
    img = cv2.imread(gemini_image_path)
    if img is None:
        print("Failed to load image")
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    print(f"Image size: {w}x{h}")

    # --- Step 1: Detect circles ---
    all_circles = []
    min_r = max(7, min(w, h) // 110)
    max_r = max(22, min(w, h) // 30)
    print(f"Radius range: {min_r} to {max_r}")

    # Parameters from analyze.py
    params = [
        (1.2, 100, 35), 
        (1.0, 80, 30), 
        (1.5, 120, 40),
        (1.0, 60, 25), 
        (1.3, 90, 32), 
        (1.0, 50, 20)
    ]

    for dp, p1, p2 in params:
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT,
            dp=dp, minDist=min_r * 1.5,
            param1=p1, param2=p2,
            minRadius=min_r, maxRadius=max_r,
        )
        if circles is not None:
            count = 0
            for cx, cy, r in np.uint16(np.around(circles))[0]:
                dup = False
                for ec in all_circles:
                    if math.sqrt((ec[0] - cx)**2 + (ec[1] - cy)**2) < min_r * 1.2:
                        dup = True
                        break
                if not dup:
                    all_circles.append((int(cx), int(cy), int(r)))
                    count += 1
            print(f"  Param(dp={dp}, p1={p1}, p2={p2}) found {count} NEW circles")

    print(f"Total unique circles detected: {len(all_circles)}")

    # Visualize
    vis = img.copy()
    for cx, cy, r in all_circles:
        cv2.circle(vis, (cx, cy), r, (0, 255, 0), 2)
    
    out_path = os.path.join(os.path.dirname(gemini_image_path), "debug_circles_output.png")
    cv2.imwrite(out_path, vis)
    print(f"Output saved to {out_path}")
    return all_circles

if __name__ == "__main__":
    base_dir = "/Users/prakashtupe/Shreeganesh/rfq-agent/backend/uploads/ballooned"
    img_path = os.path.join(base_dir, "28_ballooned.png")
    json_path = os.path.join(base_dir, "28_draft.json")
    
    if not os.path.exists(img_path):
        print(f"Image not found: {img_path}")
        sys.exit(1)
        
    with open(json_path) as f:
        data = json.load(f)
    
    features = data.get("features", [])
    json_coords = []
    expected_nums = []
    for f in features:
        pos = f.get("balloon_position")
        if pos:
            json_coords.append({"balloon_no": f["balloon_no"], "x": pos[0], "y": pos[1]})
            expected_nums.append(f["balloon_no"])
    
    _extract_balloons_from_gemini_image(img_path, json_coords, expected_nums)
