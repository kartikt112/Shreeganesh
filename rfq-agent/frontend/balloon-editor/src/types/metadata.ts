export interface MaterialSpec {
  grade: string;
  standard: string;
  heat_treatment: string;
  tensile_strength_mpa: number | null;
  yield_strength_mpa: number | null;
  hardness: string | null;
  elongation_pct: number | null;
}

export interface SurfaceProtection {
  method: string;
  standard: string;
  code: string;
  salt_spray_hours: number | null;
  salt_spray_standard: string | null;
}

export interface PartEnvelope {
  max_od_mm: number | null;
  max_id_mm: number | null;
  total_length_mm: number | null;
  is_hollow: boolean;
}

export interface TightestTolerance {
  value_mm: number | null;
  feature: string;
  balloon_no: number | null;
}

export interface ToleranceRange {
  range: string;
  tolerance: string;
}

export interface GeneralTolerances {
  linear: ToleranceRange[];
  angular: ToleranceRange[];
}

export interface ManufacturingMetadata {
  part_name: string;
  drawing_number: string;
  material: MaterialSpec;
  surface_protection: SurfaceProtection;
  part_envelope: PartEnvelope;
  tightest_tolerance: TightestTolerance;
  general_tolerance_standard: string;
  general_tolerances: GeneralTolerances;
  notes: string[];
  production_type: string;
  scale: string;
  sheet_size: string;
  issue_date: string;
  ern_number: string;
  unspecified_corner_radii_mm: number | null;
  dimensions_after_surface_treatment: boolean;
}

export interface ExtractionData {
  features: import("./feature").Feature[];
  manufacturing_metadata: ManufacturingMetadata;
  image_path?: string;
  ballooned_image_path?: string;
}
