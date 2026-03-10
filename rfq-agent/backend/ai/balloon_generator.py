"""
AI Module: Balloon Generator (Enhanced Coordinate Mode)
Uses the box_2d coordinates extracted by PyMuPDF/Gemini to precisely overlay
numbered balloon callouts directly on the engineering drawing PNG using Pillow.
"""
import os
import shutil
from typing import List, Dict, Any

def generate_ballooned_image(
    drawing_image_path: str,
    features: List[Dict[str, Any]],
    output_path: str,
    api_key: str = None
) -> str:
    """
    Reads the absolute bounding box coordinates [ymin, xmin, ymax, xmax] from features,
    and draws accurate blue balloon callouts precisely next to the dimensions.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(drawing_image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        # Determine balloon size based on image dimensions
        radius = max(18, min(w, h) // 45)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(radius * 0.9))
        except:
            font = ImageFont.load_default()

        DARK_BLUE = (31, 78, 121)
        LIGHT_BLUE = (230, 240, 250)

        for feat in features:
            num = feat.get('balloon_no')
            if not num: continue
            
            box = feat.get('box_2d')
            if box and len(box) == 4:
                # box is [ymin, xmin, ymax, xmax] in absolute pixels
                ymin, xmin, ymax, xmax = box
                
                # Plot the balloon exactly to the right of the bounding box
                cx = xmin - radius - 20
                cy = ymin + (ymax - ymin) / 2
                
                # If placing it on the left goes off standard bounds, place it on right
                if cx - radius < 0:
                    cx = xmax + radius + 20
                    
                # Draw leader line from bounding box right-edge to circle left-edge
                start_x = xmax if cx > xmax else xmin
                draw.line([(start_x, cy), (cx + (radius if cx < start_x else -radius), cy)], fill=DARK_BLUE, width=2)
                
            else:
                # Fallback location for mock features or missing coordinates
                # Just draw somewhere in the margins
                fallback_idx = num - 1
                cx = (fallback_idx % 8 + 1) * (w // 10)
                cy = (fallback_idx // 8 + 1) * (h // 10)

            # Draw the balloon circle (light blue fill, dark blue outline)
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=LIGHT_BLUE, outline=DARK_BLUE, width=2
            )
            # Draw balloon number
            text = str(num)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - tw / 2, cy - th / 2 - 2), text, fill=DARK_BLUE, font=font)

        img.save(output_path)
        print(f"[BalloonGenerator] ✅ Coordinate-based balloon overlay saved: {output_path}")
        return output_path

    except Exception as e:
        print(f"[BalloonGenerator] Error drawing balloons: {e}")
        shutil.copy(drawing_image_path, output_path)
        return output_path
