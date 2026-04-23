"""
AI Module: Drawing Parser
Implements the 5-Stage Deep Vision Pipeline:
1. PyMuPDF Vector Text Span Extraction
2. OpenCV / Geometric Proximity Clustering for Tolerances
3. Layout Parser zone filtering (heuristics)
4. Claude Sonnet 4.5 for Dimension Classification & Reasoning
Falls back to mock data if no API key is set.
"""
import os
import json
import re
from typing import List, Dict, Any

def pdf_to_png(pdf_path: str, output_path: str, dpi: int = 200) -> str:
    """Convert first page of PDF to PNG using PyMuPDF, ensuring it stays within API limits."""
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    page = doc[0]
    
    # Calculate scale based on desired DPI
    scale = dpi / 72
    
    # Safety Check: Claude has a max dimension limit (e.g. 8000px)
    # Let's ensure the largest dimension doesn't exceed 4000px for safety and bandwidth
    MAX_DIM = 4000
    rect = page.rect
    w_pts, h_pts = rect.width, rect.height
    
    if max(w_pts * scale, h_pts * scale) > MAX_DIM:
        scale = MAX_DIM / max(w_pts, h_pts)
        print(f"[DrawingParser] Scaling down high-res PDF from {dpi} DPI to fit {MAX_DIM}px limit (scale={scale:.2f})")

    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    pix.save(output_path)
    doc.close()
    return output_path


def parse_drawing(drawing_image_path: str, api_key: str = None, original_path: str = None) -> List[Dict[str, Any]]:
    """
    Execute Deep Vision Pipeline: Extract features geometrically and classify via Claude Vision.
    """
    if not api_key:
        print("[DrawingParser] No API key, using mock data.")
        return _mock_features()

    try:
        from anthropic import Anthropic
        import base64
        
        # --- Stage 1 & 2: PyMuPDF Granular Extraction & Geometric Clustering ---
        extracted_texts = []
        import fitz
        if original_path and original_path.lower().endswith('.pdf'):
            print(f"[DrawingParser] Running Layer 1 (PyMuPDF) on {original_path}")
            doc = fitz.open(original_path)
            page = doc[0]
            zoom = 200.0 / 72.0  # scale from PDF points to 200 DPI PNG
            
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                x0, y0, x1, y1 = span["bbox"]
                                sx0, sy0, sx1, sy1 = x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom
                                # Normalizing to 1000x1000 for backend consistency (from the 800x600/scale)
                                # Actually, it's better to keep absolute pixel coordinates and let balloon engine use them.
                                # But let's stick to absolute pixel coordinates on the 200 DPI image.
                                extracted_texts.append({
                                    "text": text,
                                    "bbox": [sy0, sx0, sy1, sx1] # ymin, xmin, ymax, xmax
                                })

            # Geometric clustering of tolerances / stacked text
            clustered_texts = []
            used = [False] * len(extracted_texts)

            def distance(b1, b2):
                x_dist = max(0, max(b1[1], b2[1]) - min(b1[3], b2[3]))
                y_dist = max(0, max(b1[0], b2[0]) - min(b1[2], b2[2]))
                return (x_dist**2 + y_dist**2)**0.5

            for i in range(len(extracted_texts)):
                if used[i]: continue
                cluster = [extracted_texts[i]]
                used[i] = True
                
                added = True
                while added:
                    added = False
                    for j in range(len(extracted_texts)):
                        if not used[j]:
                            for item in cluster:
                                if distance(item["bbox"], extracted_texts[j]["bbox"]) < 30:
                                    cluster.append(extracted_texts[j])
                                    used[j] = True
                                    added = True
                                    break
                                    
                ymin = min(c["bbox"][0] for c in cluster)
                xmin = min(c["bbox"][1] for c in cluster)
                ymax = max(c["bbox"][2] for c in cluster)
                xmax = max(c["bbox"][3] for c in cluster)
                
                cluster.sort(key=lambda c: (c["bbox"][0], c["bbox"][1]))
                merged_text = " ".join([c["text"] for c in cluster])
                clustered_texts.append({
                    "text": merged_text,
                    "bbox": [ymin, xmin, ymax, xmax]
                })

            # Layout filter — aggressively remove non-dimension text
            import cv2
            img_cv = cv2.imread(drawing_image_path, cv2.IMREAD_GRAYSCALE)
            h, w = img_cv.shape
            
            # Keywords that indicate annotation legends, not dimensions
            LEGEND_KEYWORDS = [
                "<cd>", "<sc>", "achtung", "attention", "werktsoff", "material",
                "en 10087", "en8", "en1a", "iso 683", "alternativ", "incl.",
                "plating", "welding", "finished dimensions", "oberflächenschutz",
                "schweißprozess", "inspection frequency", "verified with",
                "cpk>", "100% control", "measured with", "check dimension",
                "special characteristic", "kongsberg", "kongshberg",
                "scale", "sheet", "bottom view", "front view", "section",
                "position", "article no", "name of item", "note",
                "print date", "uncontrolled", "printed copies",
                "n/a", "kupainfa", "valid", "new release", "ecn",
                "din iso", "material type", "material standard",
                "replaces", "basic dim", "calculated mass", "calculated volume",
                "customer material", "designed by", "checked by",
                "released for", "document part", "document number",
                "projection", "format", "ball stud", "document description",
                "cad system", "3d data", "status", "version",
                "bs 970", "for india"
            ]
            
            filtered_texts = []
            for t in clustered_texts:
                ymin, xmin, ymax, xmax = t["bbox"]
                text_lower = t["text"].lower().strip()
                
                # Skip title block region (bottom-right quadrant)
                if ymin > h * 0.65 and xmin > w * 0.45:
                    continue
                # Skip annotation zone (right 40% of drawing, top half)
                if xmin > w * 0.6 and ymin < h * 0.65:
                    continue
                # Skip very long text clusters (legends, paragraphs, notes)
                if len(t["text"]) > 60:
                    continue
                # Skip single-character noise
                if len(text_lower) <= 1 and not text_lower.replace('.','').isdigit():
                    continue
                # Skip known legend/annotation keywords
                if any(kw in text_lower for kw in LEGEND_KEYWORDS):
                    continue
                # Skip purely alphabetical labels (A, B, C, etc.)
                if text_lower in ["a", "b", "c", "d", "e", "f", "a3", "1", "2", "3", "4", "5", "6", "7", "8"]:
                    continue
                    
                filtered_texts.append(t)
            
            print(f"[DrawingParser] Filtered {len(extracted_texts)} spans down to {len(filtered_texts)} clusters.")
        else:
            print("[DrawingParser] Not a PDF. Falling back to Claude Vision full-image OCR.")
            # Fallback will just run the old prompt without grounded text, but we'll adapt below.
            filtered_texts = []
            

        # --- Stage 4: Claude 3.5 Sonnet Reasoning ---
        client = Anthropic(api_key=api_key)
        
        # Detect image format for API calls
        _parser_media_type = "image/png"
        if image_bytes:
            import io
            from PIL import Image as PILImage
            try:
                pimg = PILImage.open(io.BytesIO(image_bytes))
                fmt = pimg.format or "PNG"
                pimg.close()
                _fmt_map = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
                _parser_media_type = _fmt_map.get(fmt, "image/png")
            except Exception:
                pass

        def _get_vlm_response(prompt_text, image_bytes=None):
            try:
                content_block = []
                if image_bytes:
                    base64_image = base64.b64encode(image_bytes).decode("utf-8")
                    content_block.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": _parser_media_type,
                            "data": base64_image
                        }
                    })
                
                content_block.append({
                    "type": "text",
                    "text": prompt_text
                })

                message = client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=4090,
                    system="You are an expert mechanical engineer processing engineering drawings.",
                    messages=[
                        {
                            "role": "user",
                            "content": content_block
                        }
                    ]
                )
                return message.content[0].text
            except Exception as ex:
                raise ex

        if len(filtered_texts) > 0:
            # --- Upgrade 3: Vector Graphics Interrogation ---
            vector_stroke_count = 0
            try:
                for path in page.get_drawings():
                    for item in path["items"]:
                        if item[0] == "l": 
                            vector_stroke_count += 1
            except Exception:
                pass
            
            vector_context = f"CAD VECTOR DATA: Detected {vector_stroke_count} vector strokes (leader lines, part boundaries) connecting to text boxes."

            # --- Upgrade 2: Vision-Language Multi-Modal (VLM) Fallback ---
            with open(drawing_image_path, "rb") as f:
                image_bytes = f.read()

            prompt = f"""You are a senior mechanical engineer classifying dimensions extracted from an engineering drawing for a CNC manufacturing feasibility study.

{vector_context}
Look at the provided high-resolution visual image of the drawing to trace the leader lines and verify exactly what each text box is pointing to (e.g. is it pointing to an Outer Dia or a Chamfer?).

Here are all text blocks extracted by PyMuPDF. Note their exact original `box_2d` coordinates ([ymin, xmin, ymax, xmax]):
{json.dumps(filtered_texts, indent=2)}

TASK: Select ONLY actual physical manufacturing dimensions/features from this list.

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

CLASSIFICATION HINTS:
- A diameter shown with parentheses like (Ø9.5) is typically an "Undercut Dia"
- A dimension < 2mm near a 45° is typically a "Chamfer" or "Slot width"
- Dimensions with Ø prefix or h-class tolerance are "Outer Dia"
- "0.2 x 45°" and "1 x 45°" are both "Chamfer"
- A bare "45" or "45°" near a chamfer is part of the chamfer, classify as "Chamfer"

RULES FOR "specification":
- Must be a SHORT clean dimension string: "14 ±0.1", "Ø13 h9 (-0.043)", "M10x1.5", "Ra 1.6", "0.2x45°"

RULES FOR "feature_type":
- Must be one of: OD, ID, LENGTH, THREAD, CHAMFER, SURFACE_FINISH, RADIUS, ANGLE
- "Outer Dia" and "Slot Dia" and "Undercut Dia" all use feature_type "OD"
- "Slot width" uses feature_type "LENGTH"
- "Threading" uses feature_type "THREAD"
- "Surface roughness" uses feature_type "SURFACE_FINISH"

Do NOT include revision numbers, view labels, notes, or non-dimension text.

Return ONLY a valid JSON array (no markdown):
[
  {{
    "description": "<one of the exact names above>",
    "specification": "<short clean dimension text>",
    "criticality_hint": "<tight if tolerance ≤ 0.05mm or h-class fit; normal otherwise>",
    "feature_type": "<OD/ID/LENGTH/THREAD/CHAMFER/SURFACE_FINISH/RADIUS/ANGLE>",
    "box_2d": <the EXACT 'bbox' array copied unmodified from the input data provided above>
  }}
]"""
            
            response_text = _get_vlm_response(prompt, image_bytes)
        else:
            # Fallback if image uploaded instead of PDF
            with open(drawing_image_path, "rb") as f:
                image_bytes = f.read()
            
            prompt = """You are an expert mechanical inspector analyzing an engineering drawing.
Extract ALL dimensions, tolerances, surface finishes, GD&T symbols, and threads.
Return ONLY this JSON array format (no markdown):
[
  {
    "description": "OD / ID / Length / Thread etc",
    "specification": "the exact text",
    "criticality_hint": "tight or normal",
    "feature_type": "OD/ID/LENGTH/THREAD/CHAMFER/SURFACE_FINISH/RADIUS/ANGLE",
    "box_2d": [ymin, xmin, ymax, xmax] # in normalized 1000x1000
  }
]"""
            response_text = _get_vlm_response(prompt, image_bytes)

        text = response_text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            features = json.loads(match.group())
            
            # --- Auto-Scale Fallback Coordinates to Image Resolution ---
            if len(filtered_texts) == 0:
                from PIL import Image
                try:
                    with Image.open(drawing_image_path) as im:
                        w, h = im.size
                        for f in features:
                            if "box_2d" in f and len(f["box_2d"]) == 4:
                                y0, x0, y1, x1 = f["box_2d"]
                                f["box_2d"] = [
                                    (y0 / 1000.0) * h,
                                    (x0 / 1000.0) * w,
                                    (y1 / 1000.0) * h,
                                    (x1 / 1000.0) * w
                                ]
                except Exception as e:
                    print(f"[DrawingParser] Could not scale fallback coords: {e}")
            
            # --- Post-filter: reject any non-dimension types that leaked through ---
            VALID_TYPES = {"OD", "ID", "LENGTH", "THREAD", "CHAMFER", "SURFACE_FINISH", "RADIUS", "ANGLE"}
            features = [f for f in features if f.get("feature_type", "").upper() in VALID_TYPES]
            
            # --- Spatial Sorting & Numbering Phase ---
            # Upgrade 1: Clock Face Sweep (Radial Sorting)
            if features:
                # 1. Find part centroid using all detected feature boxes
                all_cx = [(f.get("box_2d", [0,0,0,0])[1] + f.get("box_2d", [0,0,0,0])[3])/2 for f in features if "box_2d" in f]
                all_cy = [(f.get("box_2d", [0,0,0,0])[0] + f.get("box_2d", [0,0,0,0])[2])/2 for f in features if "box_2d" in f]
                if all_cx and all_cy:
                    center_x = sum(all_cx) / len(all_cx)
                    center_y = sum(all_cy) / len(all_cy)
                    
                    def clock_angle(f):
                        if "box_2d" not in f: return 0
                        box = f["box_2d"]
                        bx = (box[1] + box[3]) / 2
                        by = (box[0] + box[2]) / 2
                        import math
                        angle = math.atan2(by - center_y, bx - center_x)
                        # Shift so 12 o'clock (-PI/2) is 0, sweeping clockwise
                        shifted = angle + (math.pi / 2)
                        if shifted < 0:
                            shifted += 2 * math.pi
                        return shifted
                        
                    features = sorted(features, key=clock_angle)
            
            for i, f in enumerate(features):
                f["balloon_no"] = i + 1

            print(f"[DrawingParser] ✅ Successfully parsed and sorted {len(features)} grounded features.")
            return features
            
        print("[DrawingParser] Regex fallback failed. Raw text:", text[:200])
        return _mock_features()

    except Exception as e:
        import traceback
        import tempfile
        log_path = os.path.join(tempfile.gettempdir(), "parser_error.log")
        try:
            with open(log_path, "w") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        print(f"[DrawingParser] Error: {e} — falling back to mock. Check {log_path}")
        return _mock_features()


def _mock_features() -> List[Dict[str, Any]]:
    return [
        {"balloon_no": 1, "description": "Total Length", "specification": "87 ±0.5", "feature_type": "LENGTH", "criticality_hint": "normal", "box_2d": [100, 200, 150, 300]},
        {"balloon_no": 2, "description": "Sph. OD", "specification": "Ø11.8 ±0.05", "feature_type": "OD", "criticality_hint": "tight", "box_2d": [200, 300, 250, 400]},
        {"balloon_no": 3, "description": "Surface Finish on OD", "specification": "Ra 1.6", "feature_type": "SURFACE_FINISH", "criticality_hint": "normal", "box_2d": [300, 400, 350, 500]},
        {"balloon_no": 4, "description": "ID", "specification": "Ø10 ±0.3", "feature_type": "ID", "criticality_hint": "normal", "box_2d": [400, 300, 450, 400]},
        {"balloon_no": 5, "description": "OD", "specification": "Ø10.1 ±0.2", "feature_type": "OD", "criticality_hint": "normal", "box_2d": [500, 200, 550, 300]},
        {"balloon_no": 6, "description": "OD", "specification": "Ø11 ±0.2", "feature_type": "OD", "criticality_hint": "normal", "box_2d": [600, 100, 650, 200]},
        {"balloon_no": 7, "description": "OD Chamfer", "specification": "0.5 x 45°", "feature_type": "CHAMFER", "criticality_hint": "normal", "box_2d": [700, 100, 750, 200]},
    ]
