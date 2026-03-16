import fitz # PyMuPDF
import ezdxf
import math
from typing import List, Dict, Any, Tuple, Optional

def _point_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def _point_to_line_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Distance from point to a line segment."""
    l2 = (x2 - x1)**2 + (y2 - y1)**2
    if l2 == 0:
        return _point_distance(px, py, x1, y1)
    t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
    proj_x = x1 + t * (x2 - x1)
    proj_y = y1 + t * (y2 - y1)
    return _point_distance(px, py, proj_x, proj_y)

def reconstruct_dxf_dimensions(pdf_path: str, dxf_path: str, features: List[Dict[str, Any]], img_w: int, img_h: int) -> List[Dict[str, Any]]:
    """
    1. Extracts exact geometry from DXF.
    2. Builds a node diagram linking: Text Box -> Nearest Leader Line -> Next connected Geometry.
    3. Traces to find the absolute anchor coordinate where the dimension targets the geometry.
    """
    try:
        doc_pdf = fitz.open(pdf_path)
        pdf_page = doc_pdf[0]
        pdf_w = pdf_page.rect.width
        pdf_h = pdf_page.rect.height
        doc_pdf.close()
    except Exception as e:
        print(f"[DXFReconstructor] Error reading PDF for bounds: {e}")
        return features

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"[DXFReconstructor] Error reading DXF: {e}")
        return features

    # Extract geometry
    lines = []
    for e in msp.query('LINE'):
        lines.append((e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y))
        
    print(f"[DXFReconstructor] Loaded {len(lines)} raw lines from CAD data.")
    
    # Calculate exact scale mapping back and forth
    scale_x = img_w / pdf_w
    scale_y = img_h / pdf_h
    scale = (scale_x + scale_y) / 2.0
    
    updated_features = []
    
    for feat in features:
        box_px = feat.get("box_2d") # [ymin, xmin, ymax, xmax] in pixels
        if not box_px or len(box_px) != 4:
            updated_features.append(feat)
            continue
            
        ymin_px, xmin_px, ymax_px, xmax_px = box_px
        
        # Center in DXF Space
        cx_dxf = ((xmin_px + xmax_px) / 2.0) / scale
        cy_dxf = ((ymin_px + ymax_px) / 2.0) / scale
        
        # Search radius based on text box dimension - needs to be larger to catch leaders 
        # that start slightly outside the box boundary.
        box_w_dxf = (xmax_px - xmin_px) / scale
        box_h_dxf = (ymax_px - ymin_px) / scale
        search_radius_dxf = max(box_w_dxf, box_h_dxf) * 2.0
        
        # Step 1: Find the Leader Line (a line touching or very close to the text)
        leader_line = None
        closest_dist = float('inf')
        text_anchor_dxf = None
        geom_pointer_dxf = None
        
        for lx1, ly1, lx2, ly2 in lines:
            # Check if any part of the line intersects or is very close to the text box
            # First, check if endpoint is in or near the box
            dist1 = _point_distance(cx_dxf, cy_dxf, lx1, ly1)
            dist2 = _point_distance(cx_dxf, cy_dxf, lx2, ly2)
            
            # Or if the line segment passes through the expanded box
            dist_to_center = _point_to_line_dist(cx_dxf, cy_dxf, lx1, ly1, lx2, ly2)
            
            if dist_to_center < search_radius_dxf and min(dist1, dist2) > 1.0: # Ensure it's not a tiny line
                # The point near the text is the Text Anchor. The other is the Geometry Pointer.
                # Use the closest point to center as the text anchor
                if dist1 < dist2:
                    current_dist = dist1
                    current_text_anchor = (lx1, ly1)
                    current_geom_pointer = (lx2, ly2)
                else:
                    current_dist = dist2
                    current_text_anchor = (lx2, ly2)
                    current_geom_pointer = (lx1, ly1)
                    
                if current_dist < closest_dist:
                    closest_dist = current_dist
                    leader_line = (lx1, ly1, lx2, ly2)
                    text_anchor_dxf = current_text_anchor
                    geom_pointer_dxf = current_geom_pointer
                    
        if not leader_line:
            # Fallback if no leader line found
            feat["anchor_point"] = [int(xmax_px + 20), int((ymin_px + ymax_px)/2.0)]
            feat["reconstruction_status"] = "failed_no_leader"
            updated_features.append(feat)
            continue
            
        # Step 2: Traverse from Geometry Pointer to find the bounding object
        # A true leader line often points exactly to the boundary of a part or an extension line.
        # We search for any OTHER geometry entity that intersects or touches geom_pointer_dxf
        
        target_geometry = None
        target_dist = 5.0 # Tolerance in PDF points for a line connection
        best_target_pt = geom_pointer_dxf
        
        for lx1, ly1, lx2, ly2 in lines:
            # Skip the leader line itself
            if (lx1, ly1, lx2, ly2) == leader_line or (lx2, ly2, lx1, ly1) == leader_line:
                continue
                
            dist_to_segment = _point_to_line_dist(geom_pointer_dxf[0], geom_pointer_dxf[1], lx1, ly1, lx2, ly2)
            if dist_to_segment < target_dist:
                target_dist = dist_to_segment
                target_geometry = (lx1, ly1, lx2, ly2)
                # If it directly touches an endpoint, track it
                d1 = _point_distance(geom_pointer_dxf[0], geom_pointer_dxf[1], lx1, ly1)
                d2 = _point_distance(geom_pointer_dxf[0], geom_pointer_dxf[1], lx2, ly2)
                
                if d1 < d2:
                    best_target_pt = (lx1, ly1)
                else:
                    best_target_pt = (lx2, ly2)
        
        # Whether or not we found a connected intersecting geometry, the far pointer of the
        # leader line is our reconstructed absolute anchor base.
        # We prioritize the intersecting geometry exact points if found.
        
        final_x_dxf, final_y_dxf = best_target_pt
        
        # Step 3: Map Back to PNG Pixels
        anchor_x_px = int(final_x_dxf * scale)
        anchor_y_px = int(final_y_dxf * scale)
        
        # Clamp to image bounds
        anchor_x_px = max(0, min(anchor_x_px, img_w))
        anchor_y_px = max(0, min(anchor_y_px, img_h))
        
        feat["anchor_point"] = [anchor_x_px, anchor_y_px]
        if target_geometry:
            feat["reconstruction_status"] = "success_linked_geometry"
        else:
            feat["reconstruction_status"] = "success_leader_only"
            
        updated_features.append(feat)
        
    successes = sum(1 for f in updated_features if f.get("reconstruction_status", "").startswith("success"))
    print(f"[DXFReconstructor] Reconstructed {successes}/{len(features)} semantic dimensions.")
    return updated_features
