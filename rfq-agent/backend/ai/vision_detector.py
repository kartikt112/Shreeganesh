import base64
import json
import re
from typing import List, Dict, Any
from anthropic import Anthropic
from ai.prompts.vision_extraction_prompt import VISION_EXTRACTION_PROMPT

def detect_dimensions(image_path: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Step 2: AI Dimension Detection
    Uses Claude Vision 4.6 to detect dimension annotations and returns a structured list.
    """
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for vision_detector.")

    client = Anthropic(api_key=api_key)
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    # Detect format
    import imghdr
    fmt = imghdr.what(None, h=image_bytes) or "png"
    media_type = f"image/{fmt}"
    
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    
    message = client.messages.create(
        model="claude-opus-4-6", # Claude 3.5 Sonnet handles vision
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                {"type": "text", "text": VISION_EXTRACTION_PROMPT}
            ]
        }]
    )
    
    response_text = message.content[0].text.strip()
    
    # Parse JSON
    if response_text.startswith("```json"): response_text = response_text[7:]
    elif response_text.startswith("```"): response_text = response_text[3:]
    if response_text.endswith("```"): response_text = response_text[:-3]
    response_text = response_text.strip()
    
    try:
        import json_repair
        data = json_repair.loads(response_text)
        if isinstance(data, dict):
            return data.get("features", [])
        return data if isinstance(data, list) else []
    except ImportError:
        pass
        
    try:
        # We need to extract the "features" array
        match = re.search(r'\"features\"\s*:\s*\[(.*)', response_text, re.DOTALL)
        if match:
            features_text = match.group(1)
            
            # Find the last properly closed object
            last_brace_idx = features_text.rfind('}')
            if last_brace_idx != -1:
                features_text = features_text[:last_brace_idx + 1]
                
            json_str = '{"features": [' + features_text + ']}'
            data = json.loads(json_str)
            return data.get("features", [])
        else:
            data = json.loads(response_text)
            return data.get("features", [])
    except json.JSONDecodeError as e:
        print(f"[VisionDetector] Failed to parse JSON: {e}")
        import tempfile, os as _os
        dbg = _os.path.join(tempfile.gettempdir(), "vision_raw_output.txt")
        try:
            with open(dbg, "w") as rf:
                rf.write(response_text)
            print(f"[VisionDetector] Saved raw text to {dbg}")
        except OSError:
            pass
        return []

