import { useState, useEffect } from "react";
import { useBalloonStore } from "../store/balloonStore";
import type { FeatureType } from "../types/feature";

const FEATURE_TYPES: FeatureType[] = [
  "OD", "ID", "LENGTH", "CHAMFER", "THREAD", "RADIUS",
  "SURFACE_FINISH", "GDT", "ANGLE", "REFERENCE", "NOTE", "OTHER",
];

interface EditPopoverProps {
  balloonId: string | null;
  onClose: () => void;
}

export function EditPopover({ balloonId, onClose }: EditPopoverProps) {
  const { balloons, editFeature, renumberBalloon } = useBalloonStore();
  const balloon = balloons.find((b) => b.id === balloonId);

  const [spec, setSpec] = useState("");
  const [desc, setDesc] = useState("");
  const [type, setType] = useState<FeatureType>("OTHER");
  const [tolBand, setTolBand] = useState("");
  const [nomVal, setNomVal] = useState("");
  const [balloonNo, setBalloonNo] = useState("");

  useEffect(() => {
    if (balloon) {
      setSpec(balloon.feature.specification || "");
      setDesc(balloon.feature.description || "");
      setType(balloon.feature.feature_type || "OTHER");
      setTolBand(balloon.feature.tolerance_band?.toString() || "");
      setNomVal(balloon.feature.nominal_value?.toString() || "");
      setBalloonNo(balloon.feature.balloon_no.toString());
    }
  }, [balloon]);

  if (!balloon || !balloonId) return null;

  const handleSave = () => {
    const newNo = parseInt(balloonNo);
    if (!isNaN(newNo) && newNo !== balloon.feature.balloon_no) {
      renumberBalloon(balloonId, newNo);
    }

    editFeature(balloonId, {
      specification: spec,
      description: desc,
      feature_type: type,
      tolerance_band: tolBand ? parseFloat(tolBand) : null,
      nominal_value: nomVal ? parseFloat(nomVal) : null,
    });
    onClose();
  };

  return (
    <div
      style={{
        position: "fixed",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        background: "white",
        borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
        padding: 20,
        zIndex: 1000,
        minWidth: 320,
      }}
    >
      <h3 style={{ margin: "0 0 16px", fontSize: 16, color: "#1F4E79" }}>
        Edit Balloon #{balloon.feature.balloon_no}
      </h3>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label>
          <span style={labelStyle}>Balloon #</span>
          <input
            type="number"
            value={balloonNo}
            onChange={(e) => setBalloonNo(e.target.value)}
            style={inputStyle}
          />
        </label>

        <label>
          <span style={labelStyle}>Specification</span>
          <input
            value={spec}
            onChange={(e) => setSpec(e.target.value)}
            style={inputStyle}
            placeholder="e.g., Ø94 ±0.5"
          />
        </label>

        <label>
          <span style={labelStyle}>Description</span>
          <input
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            style={inputStyle}
            placeholder="e.g., Outer Dia"
          />
        </label>

        <label>
          <span style={labelStyle}>Feature Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as FeatureType)}
            style={inputStyle}
          >
            {FEATURE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <div style={{ display: "flex", gap: 10 }}>
          <label style={{ flex: 1 }}>
            <span style={labelStyle}>Tolerance Band</span>
            <input
              type="number"
              step="0.01"
              value={tolBand}
              onChange={(e) => setTolBand(e.target.value)}
              style={inputStyle}
              placeholder="mm"
            />
          </label>
          <label style={{ flex: 1 }}>
            <span style={labelStyle}>Nominal Value</span>
            <input
              type="number"
              step="0.1"
              value={nomVal}
              onChange={(e) => setNomVal(e.target.value)}
              style={inputStyle}
              placeholder="mm"
            />
          </label>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
          <button onClick={onClose} style={cancelBtnStyle}>
            Cancel
          </button>
          <button onClick={handleSave} style={saveBtnStyle}>
            Save
          </button>
        </div>
      </div>

      {/* Overlay backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.3)",
          zIndex: -1,
        }}
      />
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "#666",
  marginBottom: 3,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  border: "1px solid #ddd",
  borderRadius: 4,
  fontSize: 13,
  boxSizing: "border-box",
};

const saveBtnStyle: React.CSSProperties = {
  padding: "6px 16px",
  background: "#1F4E79",
  color: "white",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};

const cancelBtnStyle: React.CSSProperties = {
  padding: "6px 16px",
  background: "#f0f0f0",
  color: "#333",
  border: "1px solid #ddd",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};
