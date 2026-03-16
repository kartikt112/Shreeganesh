import ezdxf
import math
from typing import List, Dict, Any, Tuple

def _distance_point_to_line(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate orthogonal distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    l2 = (x2 - x1)**2 + (y2 - y1)**2
    if l2 == 0:
        return math.sqrt((px - x1)**2 + (py - y1)**2)
    
    t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
    proj_x = x1 + t * (x2 - x1)
    proj_y = y1 + t * (y2 - y1)
    return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)

def _point_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def refine_features_with_dxf(pdf_path: str, dxf_path: str, features: List[Dict[str, Any]], img_w: int, img_h: int) -> List[Dict[str, Any]]:
    """
    Parses a DXF file generated from the exact PDF to find leader lines and geometry 
    associated with extracted text features, providing high-precision anchor points.
    """
    import fitz
    try:
        doc_pdf = fitz.open(pdf_path)
        pdf_page = doc_pdf[0]
        pdf_w = pdf_page.rect.width
        pdf_h = pdf_page.rect.height
        doc_pdf.close()
    except Exception as e:
        print(f"[DXFParser] Error reading PDF for bounds: {e}")
        return features

    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"[DXFParser] Error reading DXF: {e}")
        return features

    # Extract all lines from DXF
    lines = []
    for e in msp.query('LINE'):
        lines.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
        
    print(f"[DXFParser] Loaded {len(lines)} lines from DXF.")
    
    if not lines:
        return features
        
    # The scale is exactly the ratio between the PNG dimensions and the PDF point dimensions.
    # We use img_w / pdf_w
    scale_x = img_w / pdf_w
    scale_y = img_h / pdf_h
    # Assuming uniform scaling was used in pdf_to_png
    scale = (scale_x + scale_y) / 2.0
    
    print(f"[DXFParser] Exact DXF -> PNG scale: {scale:.4f} (from PDF bounds {pdf_w}x{pdf_h} to {img_w}x{img_h})")

    updated_features = []
    
    for feat in features:
        box = feat.get("box_2d") # [ymin, xmin, ymax, xmax] in pixels
        if not box or len(box) != 4:
            updated_features.append(feat)
            continue
            
        ymin, xmin, ymax, xmax = box
        
        # Center of the text box in PNG space
        cx_png = (xmin + xmax) / 2
        cy_png = (ymin + ymax) / 2
        
        # Convert text box center to DXF space
        cx_dxf = cx_png / scale
        cy_dxf = cy_png / scale
        
        search_radius_dxf = max(xmax - xmin, ymax - ymin) / scale * 1.5
        
        # Find the line endpoint closest to the text box
        # Leader lines typically start right next to the text box
        closest_line = None
        closest_dist = float('inf')
        closest_point_dxf = None
        far_point_dxf = None
        
        for lx1, ly1, lx2, ly2 in lines:
            dist1 = _point_distance(cx_dxf, cy_dxf, lx1, ly1)
            dist2 = _point_distance(cx_dxf, cy_dxf, lx2, ly2)
            
            min_d = min(dist1, dist2)
            if min_d < search_radius_dxf and min_d < closest_dist:
                closest_dist = min_d
                closest_line = (lx1, ly1, lx2, ly2)
                if dist1 < dist2:
                    closest_point_dxf = (lx1, ly1)
                    far_point_dxf = (lx2, ly2)
                else:
                    closest_point_dxf = (lx2, ly2)
                    far_point_dxf = (lx1, ly1)
                    
        if closest_line is not None:
            # We found a leader line!
            # The 'far' point is where it points to the geometry constraint.
            # Convert back to PNG space for anchor
            anchor_x = int(far_point_dxf[0] * scale)
            anchor_y = int(far_point_dxf[1] * scale)
            
            # Simple bounds check
            anchor_x = max(0, min(anchor_x, img_w))
            anchor_y = max(0, min(anchor_y, img_h))
            
            feat["anchor_point"] = [anchor_x, anchor_y]
            feat["dxf_matched"] = True
            feat["dxf_leader_len"] = _point_distance(closest_point_dxf[0], closest_point_dxf[1], far_point_dxf[0], far_point_dxf[1]) * scale
        else:
            # Fallback to standard offset if no DXF line found
            feat["anchor_point"] = [int(xmax + 50), int(cy_png)]
            feat["dxf_matched"] = False
            
        updated_features.append(feat)
        
    matched = sum(1 for f in updated_features if f.get("dxf_matched"))
    print(f"[DXFParser] Matched DXF geometry for {matched}/{len(features)} features.")
    
    return updated_features
