from typing import List, Dict, Any

def assign_balloon_numbers(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Step 11 & 12: Numbering Logic
    Sort order: view_id -> cluster_id -> top-to-bottom.
    Assigns final sequential balloon numbers.
    """
    # Sort
    features.sort(key=lambda f: (
        f.get("view_id", 0),
        f.get("cluster_id", 0),
        f.get("anchor", [0, 0])[1], # Y coordinate
        f.get("anchor", [0, 0])[0]  # X coordinate
    ))
    
    for i, feat in enumerate(features):
        feat["balloon_no"] = i + 1
        
    return features
