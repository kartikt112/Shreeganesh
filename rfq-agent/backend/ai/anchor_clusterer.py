import numpy as np
from typing import List, Dict, Any

def cluster_anchors(features: List[Dict[str, Any]], eps: float = 60.0) -> List[Dict[str, Any]]:
    """
    Step 7: Anchor Clustering
    Groups nearby anchors within the same view using DBSCAN.
    """
    try:
        from sklearn.cluster import DBSCAN
    except ImportError:
        # Fallback if scikit-learn is not installed
        for i, f in enumerate(features):
            f["cluster_id"] = i + 1
        return features

    # Process each view separately
    view_map = {}
    for f in features:
        vid = f.get("view_id", 1)
        if vid not in view_map:
            view_map[vid] = []
        view_map[vid].append(f)
        
    cluster_offset = 0
    
    for vid, view_feats in view_map.items():
        if not view_feats:
            continue
            
        coords = np.array([f.get("anchor", [0, 0]) for f in view_feats])
        
        db = DBSCAN(eps=eps, min_samples=1).fit(coords)
        
        for feat, label in zip(view_feats, db.labels_):
            # DBSCAN assigns noise as -1, but min_samples=1 ensures all are clustered
            feat["cluster_id"] = cluster_offset + label + 1
            
        cluster_offset += len(set(db.labels_))
        
    return features
