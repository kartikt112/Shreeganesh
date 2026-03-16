import type { ManufacturingMetadata } from "../types/metadata";

interface MetadataPanelProps {
  metadata: ManufacturingMetadata | null;
}

export function MetadataPanel({ metadata }: MetadataPanelProps) {
  if (!metadata) return null;

  return (
    <div style={{ padding: 12, fontSize: 12, color: "#333" }}>
      <h4 style={{ margin: "0 0 8px", color: "#1F4E79", fontSize: 13 }}>
        Manufacturing Metadata
      </h4>

      {metadata.part_name && (
        <InfoRow label="Part" value={metadata.part_name} />
      )}
      {metadata.drawing_number && (
        <InfoRow label="Drawing #" value={metadata.drawing_number} />
      )}
      {metadata.material?.grade && (
        <InfoRow
          label="Material"
          value={`${metadata.material.grade} (${metadata.material.standard || ""})`}
        />
      )}
      {metadata.material?.heat_treatment && (
        <InfoRow label="Heat Treatment" value={metadata.material.heat_treatment} />
      )}
      {metadata.material?.tensile_strength_mpa && (
        <InfoRow
          label="Tensile"
          value={`${metadata.material.tensile_strength_mpa} MPa`}
        />
      )}
      {metadata.material?.yield_strength_mpa && (
        <InfoRow
          label="Yield"
          value={`${metadata.material.yield_strength_mpa} MPa`}
        />
      )}
      {metadata.surface_protection?.method && (
        <InfoRow label="Surface" value={metadata.surface_protection.method} />
      )}
      {metadata.surface_protection?.code && (
        <InfoRow label="Coating Code" value={metadata.surface_protection.code} />
      )}
      {metadata.tightest_tolerance?.value_mm != null && (
        <InfoRow
          label="Tightest Tol"
          value={`${metadata.tightest_tolerance.value_mm}mm (#${metadata.tightest_tolerance.balloon_no})`}
        />
      )}
      {metadata.part_envelope?.max_od_mm != null && (
        <InfoRow
          label="Part Envelope"
          value={`OD: ${metadata.part_envelope.max_od_mm}mm${
            metadata.part_envelope.max_id_mm
              ? `, ID: ${metadata.part_envelope.max_id_mm}mm`
              : ""
          }${
            metadata.part_envelope.total_length_mm
              ? `, L: ${metadata.part_envelope.total_length_mm}mm`
              : ""
          }`}
        />
      )}
      {metadata.general_tolerance_standard && (
        <InfoRow label="Gen. Tol." value={metadata.general_tolerance_standard} />
      )}
      {metadata.production_type && (
        <InfoRow label="Production" value={metadata.production_type} />
      )}

      {metadata.notes && metadata.notes.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={labelStyle}>Notes ({metadata.notes.length})</div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "#555" }}>
            {metadata.notes.slice(0, 5).map((note, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                {note.length > 80 ? note.slice(0, 80) + "..." : note}
              </li>
            ))}
            {metadata.notes.length > 5 && (
              <li style={{ fontStyle: "italic" }}>
                +{metadata.notes.length - 5} more...
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", marginBottom: 4 }}>
      <span style={labelStyle}>{label}:</span>
      <span style={{ flex: 1, fontWeight: 500 }}>{value}</span>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  minWidth: 90,
  color: "#888",
  fontSize: 11,
};
