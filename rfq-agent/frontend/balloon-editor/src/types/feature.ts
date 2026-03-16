export type FeatureType =
  | "OD"
  | "ID"
  | "LENGTH"
  | "THREAD"
  | "CHAMFER"
  | "SURFACE_FINISH"
  | "RADIUS"
  | "ANGLE"
  | "GDT"
  | "REFERENCE"
  | "NOTE"
  | "OTHER";

export interface Feature {
  balloon_no: number;
  specification: string;
  description: string;
  feature_type: FeatureType;
  criticality_hint?: "tight" | "normal";
  tolerance_band?: number | null;
  nominal_value?: number | null;
  tolerance_upper?: number | null;
  tolerance_lower?: number | null;
  surface_finish_ra?: number | null;
  gd_t_type?: string | null;
  gd_t_tolerance?: number | null;
  datum_refs?: string[];
  view_name?: string;
  bounding_box_pct?: number[] | null;
  box_2d?: number[] | null;
  confidence?: number;
  source?: "auto" | "manual";
  edited?: boolean;
}

export interface BalloonState {
  id: string;
  feature: Feature;
  x: number; // balloon circle center X (canvas pixels)
  y: number; // balloon circle center Y (canvas pixels)
  anchorX: number; // leader line anchor X
  anchorY: number; // leader line anchor Y
  selected: boolean;
  radius: number; // per-balloon radius in pixels
}

export type EditorMode = "select" | "add" | "swap" | "pan";
