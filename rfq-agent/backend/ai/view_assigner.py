from typing import List, Dict, Any

def assign_features_to_views(features: List[Dict[str, Any]], views: List[Dict[str, int]]) -> List[Dict[str, Any]]:
    """
    Step 6: Assign Features to Views
    Assigns each anchor to the view bounding box that contains it or is closest to it.
    """
    if not views:
        for f in features:
            f["view_id"] = 1
        return features
        
    for f in features:
        anchor_x, anchor_y = f.get("anchor", [0, 0])
        
        assigned_view = None
        min_dist = float('inf')
        
        for view in views:
            vx1, vy1, vx2, vy2 = view["bbox"]
            
            # Check if strictly inside
            if vx1 <= anchor_x <= vx2 and vy1 <= anchor_y <= vy2:
                assigned_view = view["view_id"]
                break
                
            # If outside, calculate distance to view center
            cx = (vx1 + vx2) / 2
            cy = (vy1 + vy2) / 2
            dist = ((anchor_x - cx)**2 + (anchor_y - cy)**2)**0.5
            
            if dist < min_dist:
                min_dist = dist
                assigned_view = view["view_id"]
                
        f["view_id"] = assigned_view or views[0]["view_id"]
        
    return features
