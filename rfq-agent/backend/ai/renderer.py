import os
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any

DARK_BLUE = (31, 78, 121)
LIGHT_BLUE = (230, 240, 250)

def render_balloons(image_path: str, features: List[Dict[str, Any]], output_path: str) -> str:
    """
    Step 12: Balloon Rendering
    Burns the balloon circle, number, and leader line sequentially into the canvas.
    """
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    # Generic font logic
    base_radius = features[0].get("balloon_radius", 20) if features else 20
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(base_radius * 0.9))
    except Exception:
        font = ImageFont.load_default()

    import math
    for feat in features:
        pos = feat.get("balloon_position")
        if not pos:
            continue
            
        cx, cy = pos
        radius = feat.get("balloon_radius", 20)
        num = feat.get("balloon_no", 0)
        
        start = feat.get("leader_start")
        end = feat.get("leader_end")
        
        # Leader line
        if start and end:
            # Recompute the leader end to touch the edge of the circle
            dx, dy = end[0] - cx, end[1] - cy
            dist = max(1, math.sqrt(dx**2 + dy**2))
            
            # Simple dog-leg bend
            sx, sy = start
            bend = None
            if abs(sx - cx) > 40 and abs(sy - cy) > 40:
                # If offset horizontally more than vertically
                if abs(sx - cx) > abs(sy - cy):
                    bend = [sx, cy]  # Straight down then over
                else:
                    bend = [cx, sy]  # Straight over then down
                    
            if bend:
                draw.line([(sx, sy), tuple(bend), (cx, cy)], fill=DARK_BLUE, width=2)
            else:
                draw.line([(sx, sy), (cx, cy)], fill=DARK_BLUE, width=2)
                
            draw.ellipse([sx-3, sy-3, sx+3, sy+3], fill=DARK_BLUE)
            
        # Circle
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     fill=LIGHT_BLUE, outline=DARK_BLUE, width=2)
                     
        # Number Text
        text = str(num)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw/2, cy - th/2 - 1), text, fill=DARK_BLUE, font=font)
        
    img.save(output_path)
    return output_path
