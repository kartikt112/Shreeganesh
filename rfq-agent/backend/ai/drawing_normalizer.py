import fitz  # PyMuPDF
import os
from typing import Dict, Any

def normalize_drawing(input_path: str, output_path: str, target_dpi: int = 300) -> Dict[str, Any]:
    """
    Step 1: Drawing Normalization
    Converts PDF to a clean grayscale high-resolution PNG using PyMuPDF.
    Returns metadata about the generated image.
    """
    if not input_path.lower().endswith('.pdf'):
        # If it's already an image, just return dimensions (simplified)
        from PIL import Image
        with Image.open(input_path) as img:
            return {"image_path": input_path, "width": img.width, "height": img.height}

    try:
        doc = fitz.open(input_path)
        page = doc[0]
        
        # Calculate scale based on desired DPI (72 is default PDF points)
        scale = target_dpi / 72.0
        
        # Limit max dimension to ~4000px to ensure API reliability and performance
        MAX_DIM = 4000
        rect = page.rect
        w_pts, h_pts = rect.width, rect.height
        
        if max(w_pts * scale, h_pts * scale) > MAX_DIM:
            scale = MAX_DIM / max(w_pts, h_pts)
            
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        pix.save(output_path)
        doc.close()
        
        return {
            "image_path": output_path,
            "width": pix.width,
            "height": pix.height
        }
    except Exception as e:
        print(f"[Normalization Failed] {e}")
        raise e
