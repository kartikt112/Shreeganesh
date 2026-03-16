import numpy as np
from typing import List, Tuple

def generate_candidates(anchor_x: int, anchor_y: int, radius: int, img_w: int, img_h: int) -> List[Tuple[int, int]]:
    """
    Step 9: Adaptive Candidate Generation
    Generates 8 radial search candidates (top, bottom, left, right, diagonals)
    at expanding radii (e.g., 60px -> 90px -> 120px) outward until valid space is found.
    """
    candidates = []
    
    # Start searching outwards (first ring at distance 60, then 90, 120, etc.)
    radii_rings = [radius * 2, radius * 3, radius * 4, radius * 6, radius * 8]
    
    angles = [
        0,              # right
        np.pi/4,        # top-right
        np.pi/2,        # top
        3*np.pi/4,      # top-left
        np.pi,          # left
        5*np.pi/4,      # bottom-left
        3*np.pi/2,      # bottom
        7*np.pi/4       # bottom-right
    ]
    
    for r in radii_rings:
        for angle in angles:
            cx = int(anchor_x + r * np.cos(angle))
            cy = int(anchor_y - r * np.sin(angle)) # Y is flipped on image
            
            # Clamp inside image
            if radius <= cx <= img_w - radius and radius <= cy <= img_h - radius:
                candidates.append((cx, cy))
                
    return candidates
