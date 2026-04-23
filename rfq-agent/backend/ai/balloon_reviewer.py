"""
AI Module: Balloon Quality Assurance Reader
Uses Claude 4.5 Sonnet to read the final ballooned drawing image.
It visually cross-references every plotted balloon number with the text it points to
and overrides any hallucinations or misclassifications from the first pass.
"""
import json
import base64
import re
from typing import List, Dict, Any

def review_balloons(
    ballooned_image_path: str,
    extracted_features: List[Dict[str, Any]],
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Passes the ballooned image to Claude to verify and correct the extracted features.
    """
    try:
        from anthropic import Anthropic
        
        from PIL import Image as PILImage

        with open(ballooned_image_path, "rb") as f:
            image_bytes = f.read()

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Detect actual format from file header
        pil_img = PILImage.open(ballooned_image_path)
        fmt = pil_img.format or "PNG"
        pil_img.close()
        fmt_map = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
        detected_media_type = fmt_map.get(fmt, "image/png")
        
        # Prepare the current JSON state so Claude knows what to correct
        current_state = json.dumps([{
            "balloon_no": f.get("balloon_no"),
            "specification": f.get("specification"),
            "description": f.get("description"),
            "feature_type": f.get("feature_type")
        } for f in extracted_features], indent=2)

        prompt = f"""You are the world's best Mechanical Engineer and Lead Quality Inspector. You are incredibly detail-oriented and have decades of experience checking engineering drawings, GD&T, and manufacturing prints.

I have run an initial, automated AI script to extract dimensions for a feasibility report and overlay numbered balloons on the drawing. Here is the JSON output it produced:
{current_state}

YOUR CRITICAL MISSION:
You must perform a final QA check on the ballooning and extracted data before it gets sent to the Costing and Feasibility Engine.
1. Find every blue balloon number visually on the attached drawing.
2. Follow its line precisely to the exact dimension, tolerance, or text it is pointing to.
3. Compare the visual reality to the JSON data above.
4. Correct ANY mistakes (hallucinated dimensions, missed negative tolerances, wrong types, wrong descriptions).
5. If the JSON missed a critical tolerance or misread a number, YOU MUST fix it. Our feasibility report depends on this accuracy.
6. Only return the features that ACTUALLY EXIST and are pointed to by a balloon. If a balloon number is pointing to empty space or a non-dimension, remove it.

RULES FOR "description" — use EXACTLY one of these names:
  - "Outer Dia" for outer diameters (Ø with tolerance, or h-class fits like 13h9)
  - "Slot Dia" for slot/groove diameters (internal slot openings)
  - "Undercut Dia" for undercut/relief diameters (usually parenthesized like (Ø9.5))
  - "Length" for straight linear dimensions (e.g. 25 ±0.2, 5.5, 20 ±1)
  - "Slot width" for slot/groove widths (narrow features like 1.2)
  - "Threading" for thread callouts (e.g. M10x1.5)
  - "Chamfer" for chamfers (e.g. 0.2x45°, 1x45°)
  - "Surface roughness" for Ra values (e.g. Ra 1.6)
  - "Angle" for angle dimensions (e.g. 20° ±1°)
  - "Radius" for standard radii
  - "Note" for text blocks and GD&T boxes

RULES FOR "feature_type":
- Must be one of: OD, ID, LENGTH, THREAD, CHAMFER, SURFACE_FINISH, RADIUS, ANGLE, NOTE

Return the entirely CORRECTED JSON array (no markdown):
[
  {{
    "balloon_no": <int>,
    "specification": "<the precise dimension text>",
    "description": "<one of the exact names above>",
    "feature_type": "<OD/ID/LENGTH/THREAD/CHAMFER/SURFACE_FINISH/RADIUS/ANGLE/NOTE>"
  }}
]"""

        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4090,
            system="You are the world's best Mechanical Engineer and Lead Quality Inspector.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": detected_media_type,
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        text = message.content[0].text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            corrected_list = json.loads(match.group())
            
            # Map the corrected data back into the original features (to keep database IDs/boxes)
            corrected_dict = {str(item.get("balloon_no")): item for item in corrected_list}
            
            final_features = []
            for f in extracted_features:
                bno = str(f.get("balloon_no"))
                if bno in corrected_dict:
                    correction = corrected_dict[bno]
                    f["specification"] = correction.get("specification", f["specification"])
                    f["description"] = correction.get("description", f["description"])
                    f["feature_type"] = correction.get("feature_type", f["feature_type"])
                    # If tolerance is tight (contains parenthesis or <0.05), mark tight
                    spec = f["specification"]
                    if "(" in spec or "h" in spec or "H" in spec:
                        f["criticality_hint"] = "tight"
                    else:
                        f["criticality_hint"] = "normal"
                    final_features.append(f)
            
            print(f"[BalloonReviewer] QA passed! Auto-corrected {len(final_features)} dimensions vis-a-vis the overlaid balloons.")
            return final_features
        else:
            print("[BalloonReviewer] Failed to parse JSON from Claude. Keeping original.")
            return extracted_features

    except Exception as e:
        print(f"[BalloonReviewer] QA Error: {e}. Keeping original features.")
        return extracted_features
