"""One-shot A/B: Claude Opus 4.6 vs Gemini 2.5 Pro on a real drawing.

Runs the SAME production prompt/extracted-text through both models and
reports timing, token usage, parsed-feature count, and the raw JSON so
you can eyeball accuracy.

Usage:
    python model_bakeoff.py /path/to/drawing.pdf
"""

from __future__ import annotations
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import fitz
from dotenv import load_dotenv

load_dotenv()

# ---- config --------------------------------------------------------------
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
VERTEX_API_KEY = os.getenv("VERTEX_API_KEY") or os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def pdf_to_png(pdf_path: Path) -> tuple[bytes, list[dict]]:
    """Render page 1 of the PDF to PNG bytes and pre-extract clustered text with PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    zoom = 200.0 / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    png_bytes = pix.tobytes("png")

    text_dict = page.get_text("dict")
    raw = []
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "").strip()
                if not txt:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                raw.append(
                    {
                        "text": txt,
                        "bbox": [y0 * zoom, x0 * zoom, y1 * zoom, x1 * zoom],
                    }
                )

    # Simple geometric clustering matching drawing_parser.py
    used = [False] * len(raw)

    def dist(b1, b2):
        x = max(0, max(b1[1], b2[1]) - min(b1[3], b2[3]))
        y = max(0, max(b1[0], b2[0]) - min(b1[2], b2[2]))
        return (x * x + y * y) ** 0.5

    clusters = []
    for i in range(len(raw)):
        if used[i]:
            continue
        bucket = [raw[i]]
        used[i] = True
        added = True
        while added:
            added = False
            for j in range(len(raw)):
                if used[j]:
                    continue
                for item in bucket:
                    if dist(item["bbox"], raw[j]["bbox"]) < 30:
                        bucket.append(raw[j])
                        used[j] = True
                        added = True
                        break
        ymin = min(b["bbox"][0] for b in bucket)
        xmin = min(b["bbox"][1] for b in bucket)
        ymax = max(b["bbox"][2] for b in bucket)
        xmax = max(b["bbox"][3] for b in bucket)
        bucket.sort(key=lambda c: (c["bbox"][0], c["bbox"][1]))
        clusters.append(
            {"text": " ".join(b["text"] for b in bucket), "bbox": [ymin, xmin, ymax, xmax]}
        )

    doc.close()
    return png_bytes, clusters


def build_prompt(clusters: list[dict]) -> str:
    return f"""You are a senior mechanical engineer classifying dimensions extracted from an engineering drawing for a CNC manufacturing feasibility study.

Look at the provided high-resolution visual image of the drawing to trace leader lines and verify what each text box is pointing to.

Here are all text blocks extracted by PyMuPDF with exact `bbox` coordinates ([ymin, xmin, ymax, xmax]):
{json.dumps(clusters, indent=2)}

TASK: Select ONLY actual physical manufacturing dimensions/features.

RULES FOR "description" — use EXACTLY one of:
  - "Outer Dia"  (Ø with tolerance, h-class fits)
  - "Slot Dia" / "Undercut Dia"
  - "Length" (linear)
  - "Slot width"
  - "Threading" (e.g. M10x1.5)
  - "Chamfer" (e.g. 0.2x45°)
  - "Surface roughness" (Ra values)
  - "Angle"

RULES FOR "feature_type": one of OD, ID, LENGTH, THREAD, CHAMFER, SURFACE_FINISH, RADIUS, ANGLE.

Return ONLY valid JSON array (no markdown):
[
  {{
    "description": "<name>",
    "specification": "<short clean string>",
    "criticality_hint": "tight|normal",
    "feature_type": "<type>",
    "box_2d": <copied unmodified from input>
  }}
]"""


def extract_json_array(text: str):
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        return None


def run_claude(png: bytes, prompt: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY missing"}
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    t0 = time.time()
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4090,
        system="You are an expert mechanical engineer processing engineering drawings.",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(png).decode(),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    dt = time.time() - t0
    text = msg.content[0].text
    parsed = extract_json_array(text)
    return {
        "model": CLAUDE_MODEL,
        "elapsed_s": round(dt, 2),
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "raw": text,
        "features": parsed,
        "feature_count": len(parsed) if parsed else 0,
    }


def run_gemini(png: bytes, prompt: str) -> dict:
    if not VERTEX_API_KEY:
        return {"error": "VERTEX_API_KEY / GOOGLE_API_KEY missing"}
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, api_key=VERTEX_API_KEY)
    t0 = time.time()
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=png, mime_type="image/png"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            system_instruction="You are an expert mechanical engineer processing engineering drawings.",
            max_output_tokens=4096,
            temperature=0.0,
        ),
    )
    dt = time.time() - t0
    text = resp.text or ""
    parsed = extract_json_array(text)
    usage = resp.usage_metadata
    return {
        "model": GEMINI_MODEL,
        "elapsed_s": round(dt, 2),
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "raw": text,
        "features": parsed,
        "feature_count": len(parsed) if parsed else 0,
    }


def estimate_cost(name: str, in_toks: int | None, out_toks: int | None) -> str:
    if in_toks is None or out_toks is None:
        return "n/a"
    # Public list prices (per 1M tokens) as of early 2026:
    prices = {
        "claude-opus-4-6": (15.0, 75.0),
        "claude-sonnet-4-6": (3.0, 15.0),
        "gemini-2.5-pro": (1.25, 10.0),
        "gemini-2.5-flash": (0.30, 2.50),
    }
    for prefix, (pi, po) in prices.items():
        if name.startswith(prefix):
            c = (in_toks / 1_000_000) * pi + (out_toks / 1_000_000) * po
            return f"${c:.4f}"
    return "n/a"


def print_result(name: str, r: dict):
    print(f"\n{'=' * 70}")
    print(f"  {name}: {r.get('model', '?')}")
    print("=" * 70)
    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return
    print(f"  latency:        {r['elapsed_s']}s")
    print(f"  tokens in/out:  {r['input_tokens']} / {r['output_tokens']}")
    print(f"  cost estimate:  {estimate_cost(r['model'], r['input_tokens'], r['output_tokens'])}")
    print(f"  features:       {r['feature_count']} parsed")
    print(f"  json valid:     {'YES' if r['features'] is not None else 'NO'}")
    if r.get("features"):
        print("\n  sample (first 5):")
        for f in r["features"][:5]:
            desc = f.get("description", "?")
            spec = f.get("specification", "?")
            ft = f.get("feature_type", "?")
            print(f"    - [{ft:>14}] {desc:<20} → {spec}")


def main():
    if len(sys.argv) < 2:
        pdf = Path("/Users/prakashtupe/Shreeganesh/Swivel_tube.pdf")
    else:
        pdf = Path(sys.argv[1])
    if not pdf.exists():
        print(f"PDF not found: {pdf}")
        sys.exit(1)

    print(f"PDF: {pdf.name} ({pdf.stat().st_size / 1024:.0f} KB)")
    print("Rendering page 1 at 200 DPI + extracting text with PyMuPDF…")
    png, clusters = pdf_to_png(pdf)
    print(f"  image: {len(png)} bytes, text clusters: {len(clusters)}")

    prompt = build_prompt(clusters)

    print("\nCalling Claude…")
    c = run_claude(png, prompt)
    print("Calling Gemini (Vertex)…")
    g = run_gemini(png, prompt)

    print_result("CLAUDE", c)
    print_result("GEMINI", g)

    print("\n" + "=" * 70)
    print("  COMPARISON SUMMARY")
    print("=" * 70)

    def cell(k, r):
        return f"{r.get(k, '—')}" if "error" not in r else "ERR"

    print(f"  {'metric':<20}{'Claude':<20}{'Gemini':<20}")
    print(f"  {'-' * 60}")
    print(f"  {'latency (s)':<20}{cell('elapsed_s', c):<20}{cell('elapsed_s', g):<20}")
    print(f"  {'input tokens':<20}{cell('input_tokens', c):<20}{cell('input_tokens', g):<20}")
    print(f"  {'output tokens':<20}{cell('output_tokens', c):<20}{cell('output_tokens', g):<20}")
    cc = estimate_cost(c.get("model", ""), c.get("input_tokens"), c.get("output_tokens")) if "error" not in c else "—"
    gc = estimate_cost(g.get("model", ""), g.get("input_tokens"), g.get("output_tokens")) if "error" not in g else "—"
    print(f"  {'cost/call':<20}{cc:<20}{gc:<20}")
    print(f"  {'features parsed':<20}{cell('feature_count', c):<20}{cell('feature_count', g):<20}")

    # Write full outputs to disk for deeper inspection.
    out = Path("/tmp/bakeoff_results.json")
    out.write_text(
        json.dumps(
            {
                "pdf": str(pdf),
                "claude": c,
                "gemini": g,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nFull outputs (with raw JSON) saved to: {out}")


if __name__ == "__main__":
    main()
