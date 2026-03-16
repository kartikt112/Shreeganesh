import base64
import json
import re
from typing import List, Dict, Any
from anthropic import Anthropic

def validate_balloons(image_path: str, features: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """
    Step 13: QA Validation
    Sends the generated ballooned drawing to Claude Vision to verify for duplicates, missing annotations, or overlapping text.
    Returns structurally identical but potentially corrected features list.
    """
    if not api_key:
        print("[QAValidator] Skipping due to missing API key")
        return features
        
    client = Anthropic(api_key=api_key)
    with open(image_path, "rb") as f:
        image_bytes = f.read()
        
    import imghdr
    fmt = imghdr.what(None, h=image_bytes) or "png"
    media_type = f"image/{fmt}"
    
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    prompt = f"""You are a QA Inspector reviewing a ballooned drawing.
There are {len(features)} nominal dimensions expected.

Verify the following:
1. Are there any obviously overlapping balloons that obscure numbers?
2. Did we miss attaching a balloon to a major dimension?
3. Are there duplicate balloon numbers?

Do not hallucinate features.
If the drawing is acceptable or only has minor overlaps, output "status: pass".
Otherwise, output "status: fail" and concisely list what needs correction.
"""
    
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    
    response_text = message.content[0].text.strip()
    
    # Simple heuristic logging
    if "status: pass" in response_text.lower():
        print("[QAValidator] Output passed AI visual inspection.")
    else:
        print(f"[QAValidator] AI raised concerns:\n{response_text[:300]}")
        
    # Standard implementation just returns features.
    # A full AI auto-fix loop would parse the QA text and rerun coordinate placement here.
    return features
