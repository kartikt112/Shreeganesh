import type { Feature } from "../types/feature";
import type { ManufacturingMetadata, ExtractionData } from "../types/metadata";

const FEATURE_TYPES = [
  "OD", "ID", "LENGTH", "THREAD", "CHAMFER", "SURFACE_FINISH",
  "RADIUS", "ANGLE", "GDT", "REFERENCE", "NOTE", "OTHER",
];

export function validateFeature(f: unknown): f is Feature {
  if (typeof f !== "object" || f === null) return false;
  const obj = f as Record<string, unknown>;
  return (
    typeof obj.balloon_no === "number" &&
    typeof obj.specification === "string" &&
    typeof obj.description === "string"
  );
}

export function validateExtractionData(data: unknown): data is ExtractionData {
  if (typeof data !== "object" || data === null) return false;
  const obj = data as Record<string, unknown>;
  if (!Array.isArray(obj.features)) return false;
  return obj.features.every(validateFeature);
}

export async function loadFromFile(
  file: File
): Promise<ExtractionData> {
  const text = await file.text();
  const parsed = JSON.parse(text);

  if (validateExtractionData(parsed)) {
    return parsed;
  }

  // Try treating as plain features array
  if (Array.isArray(parsed) && parsed.every(validateFeature)) {
    return {
      features: parsed,
      manufacturing_metadata: emptyMetadata(),
    };
  }

  throw new Error("Invalid JSON format: expected { features: [...], manufacturing_metadata: {...} }");
}

export async function loadFromUrl(
  dataUrl: string
): Promise<ExtractionData> {
  const resp = await fetch(dataUrl);
  if (!resp.ok) {
    throw new Error(`Failed to fetch data: ${resp.status}`);
  }
  const data = await resp.json();
  if (validateExtractionData(data)) {
    return data;
  }
  throw new Error("Invalid data format from URL");
}

export async function loadFromApiEndpoint(
  rfqId: number,
  baseUrl: string = "http://localhost:8000"
): Promise<ExtractionData> {
  const resp = await fetch(`${baseUrl}/api/rfq/${rfqId}/extraction-data`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch RFQ ${rfqId} data: ${resp.status}`);
  }
  return resp.json();
}

export function parseFromText(text: string): ExtractionData {
  const parsed = JSON.parse(text);
  if (validateExtractionData(parsed)) {
    return parsed;
  }
  if (Array.isArray(parsed) && parsed.every(validateFeature)) {
    return {
      features: parsed,
      manufacturing_metadata: emptyMetadata(),
    };
  }
  throw new Error("Invalid JSON format");
}

function emptyMetadata(): ManufacturingMetadata {
  return {
    part_name: "",
    drawing_number: "",
    material: {
      grade: "",
      standard: "",
      heat_treatment: "",
      tensile_strength_mpa: null,
      yield_strength_mpa: null,
      hardness: null,
      elongation_pct: null,
    },
    surface_protection: {
      method: "",
      standard: "",
      code: "",
      salt_spray_hours: null,
      salt_spray_standard: null,
    },
    part_envelope: {
      max_od_mm: null,
      max_id_mm: null,
      total_length_mm: null,
      is_hollow: false,
    },
    tightest_tolerance: {
      value_mm: null,
      feature: "",
      balloon_no: null,
    },
    general_tolerance_standard: "",
    general_tolerances: { linear: [], angular: [] },
    notes: [],
    production_type: "",
    scale: "",
    sheet_size: "",
    issue_date: "",
    ern_number: "",
    unspecified_corner_radii_mm: null,
    dimensions_after_surface_treatment: false,
  };
}
