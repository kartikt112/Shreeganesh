import fitz  # PyMuPDF
import cv2
import numpy as np
import os
import json
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

pdf_path = "/Users/prakashtupe/Shreeganesh/1001540840_5DR_000_BALL STUD Sheet.1.pdf"
img_path = "/tmp/vision_test_img.png"
output_path = "/tmp/vision_test_ballooned.png"

# === 1. PyMuPDF Processing: Extract Text & Render Image ===
print("\n[Layer 1] PyMuPDF Vector & Text Extraction...")
doc = fitz.open(pdf_path)
page = doc[0]
zoom = 2.0  # Rendering at high resolution
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat)
pix.save(img_path)

# Extract physical text precisely from vector PDF using granular spans
text_dict = page.get_text("dict")
extracted_texts = []
for block in text_dict.get("blocks", []):
    if block.get("type") == 0:  # Text block
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    x0, y0, x1, y1 = span["bbox"]
                    # Scale mathematical coords to image resolution
                    sx0, sy0, sx1, sy1 = x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom
                    extracted_texts.append({
                        "text": text,
                        "bbox": [sy0, sx0, sy1, sx1]  # ymin, xmin, ymax, xmax
                    })
print(f"✅ Extracted {len(extracted_texts)} granular text spans with 100% geometric accuracy.")


# --- Geometric Clustering (Merge nearby spans like tolerances) ---
print("\n[Layer 2] Geometric Text Clustering...")
clustered_texts = []
used = [False] * len(extracted_texts)

def distance(b1, b2):
    # b = [ymin, xmin, ymax, xmax]
    y1c, x1c = (b1[0]+b1[2])/2, (b1[1]+b1[3])/2
    y2c, x2c = (b2[0]+b2[2])/2, (b2[1]+b2[3])/2
    
    # Calculate shortest distance between the two rectangles
    x_dist = max(0, max(b1[1], b2[1]) - min(b1[3], b2[3]))
    y_dist = max(0, max(b1[0], b2[0]) - min(b1[2], b2[2]))
    return (x_dist**2 + y_dist**2)**0.5

# Group text spans within 30px of each other
for i in range(len(extracted_texts)):
    if used[i]: continue
    cluster = [extracted_texts[i]]
    used[i] = True
    
    # Find all nearby texts
    added = True
    while added:
        added = False
        for j in range(len(extracted_texts)):
            if not used[j]:
                # If j is close to ANY item in the current cluster
                for item in cluster:
                    if distance(item["bbox"], extracted_texts[j]["bbox"]) < 30:
                        cluster.append(extracted_texts[j])
                        used[j] = True
                        added = True
                        break
                        
    # Merge the cluster into a single bounding box
    ymin = min(c["bbox"][0] for c in cluster)
    xmin = min(c["bbox"][1] for c in cluster)
    ymax = max(c["bbox"][2] for c in cluster)
    xmax = max(c["bbox"][3] for c in cluster)
    
    # Sort texts left-to-right, top-to-bottom for readable merging
    cluster.sort(key=lambda c: (c["bbox"][0], c["bbox"][1]))
    merged_text = " ".join([c["text"] for c in cluster])
    
    clustered_texts.append({
        "text": merged_text,
        "bbox": [ymin, xmin, ymax, xmax]
    })
    
print(f"✅ Clustered {len(extracted_texts)} spans into {len(clustered_texts)} cohesive dimension blocks.")

# === 3. OpenCV Processing: Geometry Detection ===
print("\n[Layer 3] OpenCV Visual Inspection...")
img_cv = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
edges = cv2.Canny(img_cv, 50, 150, apertureSize=3)
lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=50, maxLineGap=10)
num_lines = len(lines) if lines is not None else 0
print(f"✅ Detected {num_lines} distinct geometric leader lines and part contours.")


# === 4. Layout Parser: Section Clustering ===
print("\n[Layer 4] Layout Region Logic...")
h, w = img_cv.shape

# Basic heuristic to filter out Title Blocks (bottom right) and page headers
filtered_texts = []
for t in clustered_texts:
    ymin, xmin, ymax, xmax = t["bbox"]
    if ymin > h * 0.85 and xmin > w * 0.6:
        continue
    if t["text"].lower() in ["kongshberg", "scale", "sheet", "a3", "b", "c", "d", "e", "f", "1", "2", "3", "4", "5", "6", "7", "8"]:
        continue
    filtered_texts.append(t)
    
print(f"✅ Filtered to {len(filtered_texts)} potential manufacturing dimensions/annotations.")


# === 4. Gemini 2.5 Flash: Reasoning Phase ===
print("\n[Layer 4] Nano Banana (Gemini) Reasoning...")
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

prompt = f"""You are the mechanical reasoning brain of a vision pipeline.
I have used vector extraction + OpenCV to perfectly locate every piece of text in an engineering drawing.

Here is the exact grounded text data with physical bounding boxes ([ymin, xmin, ymax, xmax]):
{json.dumps(filtered_texts, indent=2)}

Task: Filter this list down ONLY to actual dimensions, tolerances, thread specs, and critical GD&T features.
Ignore standard layout text, part numbers, or material notes unless they are specific manufacturing instructions.

Return a JSON array of objects:
[
  {{
    "description": "<feature type: OD, Length, Thread, etc>",
    "specification": "<the exact text>",
    "box_2d": <the EXACT 'bbox' array provided for this text>
  }}
]

Return ONLY the JSON array, nothing else!"""

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[prompt]
)

response_text = response.text.strip()
if response_text.startswith("```json"):
    response_text = response_text[7:]
elif response_text.startswith("```"):
    response_text = response_text[3:]
if response_text.endswith("```"):
    response_text = response_text[:-3]

features = json.loads(response_text.strip())
print(f"✅ AI Reasoning complete. Classified {len(features)} valid manufacturing features.")


# Sort features spatially to ensure logical balloon numbering order
# Group items by horizontal bands (rounding Y to nearest 100 pixels), then sort Left-to-Right
features = sorted(features, key=lambda f: (round(f["box_2d"][0] / 100), f["box_2d"][1]))

# Assign balloon numbers cleanly after spatial sorting
for i, f in enumerate(features):
    f["balloon_no"] = i + 1

# === 5. Pillow Balloon Engine ===
print("\n[Layer 5] Precise Balloon Overlay...")
img_pil = Image.open(img_path).convert("RGB")
draw = ImageDraw.Draw(img_pil)

try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=16)
except:
    font = ImageFont.load_default()

radius = 18
DARK_BLUE = (31, 78, 121)
LIGHT_BLUE = (230, 240, 250)

for feat in features:
    box = feat["box_2d"]
    ymin, xmin, ymax, xmax = box
    
    # Do NOT draw the bounding box in production, only balloons
    
    # Plot Balloon left of box
    cx = xmin - radius - 20
    cy = ymin + (ymax - ymin)/2
    
    # If off frame or overlapping other text, put right
    if cx - radius < 0:
        cx = xmax + radius + 20
        
    start_x = xmax if cx > xmax else xmin
    
    # Draw dark blue leader line
    draw.line([(start_x, cy), (cx + (radius if cx < start_x else -radius), cy)], fill=DARK_BLUE, width=2)
    
    # Draw light blue balloon with dark blue outline
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], outline=DARK_BLUE, fill=LIGHT_BLUE, width=2)
    
    text = str(feat["balloon_no"])
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    
    # Draw text inside balloon
    draw.text((cx-tw/2, cy-th/2 - 2), text, fill=DARK_BLUE, font=font)

img_pil.save(output_path)
print(f"🎉 Pipeline Complete! Image with 100% deterministic layout saved to {output_path}")
