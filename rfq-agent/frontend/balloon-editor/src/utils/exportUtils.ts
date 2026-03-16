import Konva from "konva";
import Papa from "papaparse";
import type { Feature } from "../types/feature";
import type { ManufacturingMetadata } from "../types/metadata";

export function exportPNG(stage: Konva.Stage, filename?: string) {
  const dataUrl = stage.toDataURL({ pixelRatio: 1 });
  const link = document.createElement("a");
  link.download = filename || `ballooned_${Date.now()}.png`;
  link.href = dataUrl;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function exportJSON(
  features: Feature[],
  metadata: ManufacturingMetadata | null,
  filename?: string
) {
  const output = {
    features,
    manufacturing_metadata: metadata || {},
  };
  const blob = new Blob([JSON.stringify(output, null, 2)], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.download = filename || `features_${Date.now()}.json`;
  link.href = URL.createObjectURL(blob);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

export function exportCSV(features: Feature[], filename?: string) {
  const rows = features.map((f) => ({
    balloon_no: f.balloon_no,
    specification: f.specification,
    description: f.description,
    feature_type: f.feature_type,
    tolerance_band: f.tolerance_band ?? "",
    nominal_value: f.nominal_value ?? "",
    box_2d: f.box_2d ? JSON.stringify(f.box_2d) : "",
    confidence: f.confidence ?? "",
    source: f.source ?? "auto",
    edited: f.edited ? "Yes" : "No",
  }));

  const csv = Papa.unparse(rows);
  const blob = new Blob([csv], { type: "text/csv" });
  const link = document.createElement("a");
  link.download = filename || `features_${Date.now()}.csv`;
  link.href = URL.createObjectURL(blob);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}
