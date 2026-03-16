from typing import List, Dict, Any

def construct_feature_graph(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Step 4: Feature Graph Construction
    Normalizes the feature array to ensure consistent structure for downstream.
    Connects dimension text, leader lines, and nearby geometry into a standard format.
    """
    graph_nodes = []
    
    for idx, raw_feat in enumerate(features):
        feature_id = raw_feat.get("balloon_no", idx + 1)
        
        node = {
            "id": feature_id,
            "dimension_text": raw_feat.get("specification", ""),
            "description": raw_feat.get("description", ""),
            "feature_type": raw_feat.get("feature_type", "OTHER"),
            "bbox": raw_feat.get("bbox", [0, 0, 0, 0]),     # [ymin, xmin, ymax, xmax]
            "anchor": raw_feat.get("anchor", [0, 0]),       # [x, y]
            
            # Fields populated in later steps
            "view_id": None,
            "cluster_id": None,
            "balloon_position": None,
            "balloon_radius": None,
            
            # Leader layout
            "leader_start": None,
            "leader_bend": None,
            "leader_end": None,
            
            # Store the original vision metadata
            "metadata": raw_feat
        }
        graph_nodes.append(node)
        
    return graph_nodes
