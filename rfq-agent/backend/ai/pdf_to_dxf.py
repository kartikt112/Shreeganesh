import fitz  # PyMuPDF
import ezdxf
import os
import math
from typing import List, Tuple

def extract_pdf_to_dxf(pdf_path: str, output_dxf_path: str) -> bool:
    """
    Extracts vector drawings from a PDF and converts them to a DXF file.
    
    Args:
        pdf_path: Path to the input PDF file.
        output_dxf_path: Path to the output DXF file.
        
    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(pdf_path):
        print(f"[PDF2DXF] Error: Input PDF not found: {pdf_path}")
        return False

    print(f"[PDF2DXF] Converting {os.path.basename(pdf_path)} to DXF...")
    
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            print("[PDF2DXF] Error: PDF has no pages.")
            return False
            
        page = doc[0]  # Just process the first page for engineering drawings
        
        # Create a new DXF document. R2010 is a good modern standard.
        dxf_doc = ezdxf.new('R2010')
        msp = dxf_doc.modelspace()
        
        # Establish a 'Vectors' layer
        dxf_doc.layers.new(name='Vectors', dxfattribs={'color': 7}) # 7 is black/white
        
        # Get raw vector paths from PyMuPDF
        drawings = page.get_drawings()
        
        # PDF coordinates: (0,0) is top-left.
        # DXF coordinates: Usually (0,0) is bottom-left, but for 1:1 pixel mapping
        # to our OpenCV PNG pipeline, we will keep the native coordinates 
        # (or just invert Y if strictly necessary for standard CAD, but our AI 
        # operates top-left origin).
        
        # We will directly draw the paths into DXF
        lines_drawn = 0
        arcs_drawn = 0
        
        for path in drawings:
            # Each 'path' is a dict containing drawing items
            for item in path.get("items", []):
                cmd = item[0]
                
                # PyMuPDF Path commands: 
                # "l" = line
                # "c" = cubic bezier
                # "re" = rectangle
                
                if cmd == "l":
                    # Line: ("l", p1, p2)
                    p1, p2 = item[1], item[2]
                    # Map top-left PyMuPDF to top-left DXF (we'll just use the raw coordinates)
                    msp.add_line((p1.x, p1.y), (p2.x, p2.y), dxfattribs={'layer': 'Vectors'})
                    lines_drawn += 1
                    
                elif cmd == "re":
                    # Rectangle: ("re", fitz.Rect)
                    rect = item[1]
                    # Draw 4 lines for the rectangle
                    p1 = (rect.x0, rect.y0)
                    p2 = (rect.x1, rect.y0)
                    p3 = (rect.x1, rect.y1)
                    p4 = (rect.x0, rect.y1)
                    msp.add_line(p1, p2, dxfattribs={'layer': 'Vectors'})
                    msp.add_line(p2, p3, dxfattribs={'layer': 'Vectors'})
                    msp.add_line(p3, p4, dxfattribs={'layer': 'Vectors'})
                    msp.add_line(p4, p1, dxfattribs={'layer': 'Vectors'})
                    lines_drawn += 4
                    
                elif cmd == "c":
                    # Cubic Bezier: ("c", p1, p2, p3, p4) - curve from p1 to p4 using p2, p3 as control points.
                    # ezdxf allows adding spline entities directly
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    msp.add_spline(fit_points=[(p1.x, p1.y), (p2.x, p2.y), (p3.x, p3.y), (p4.x, p4.y)], dxfattribs={'layer': 'Vectors'})
                    arcs_drawn += 1

        dxf_doc.saveas(output_dxf_path)
        print(f"[PDF2DXF] Successfully saved DXF to {output_dxf_path}")
        print(f"[PDF2DXF] Extracted {lines_drawn} lines and {arcs_drawn} curves.")
        return True

    except Exception as e:
        print(f"[PDF2DXF] Error generating DXF: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        extract_pdf_to_dxf(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python pdf_to_dxf.py input.pdf output.dxf")
