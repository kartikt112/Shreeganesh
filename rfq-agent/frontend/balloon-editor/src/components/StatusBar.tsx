import { useBalloonStore } from "../store/balloonStore";

const MODE_LABELS: Record<string, string> = {
  select: "Select",
  add: "Add Balloon",
  swap: "Swap Numbers",
};

const MODE_COLORS: Record<string, string> = {
  select: "#64748b",
  add: "#3b82f6",
  swap: "#a855f7",
};

export function StatusBar() {
  const { balloons, zoom, mode, gridSnap } = useBalloonStore();

  const autoCount   = balloons.filter((b) => b.feature.source !== "manual").length;
  const manualCount = balloons.filter((b) => b.feature.source === "manual").length;
  const editedCount = balloons.filter((b) => b.feature.edited).length;
  const modeColor   = MODE_COLORS[mode] || "#64748b";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "0 14px",
        height: 26,
        background: "#070a0f",
        borderTop: "1px solid #1a2235",
        color: "#4a5568",
        fontSize: 11,
        fontFamily: "Inter, -apple-system, sans-serif",
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      {/* Mode badge */}
      <div style={{
        display: "flex", alignItems: "center", gap: 5,
        marginRight: 14, paddingRight: 14,
        borderRight: "1px solid #1a2235",
      }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: modeColor }} />
        <span style={{ color: modeColor, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 10 }}>
          {MODE_LABELS[mode] || mode}
        </span>
      </div>

      {/* Stats */}
      <StatusItem label="Balloons" value={String(balloons.length)} />
      <StatusSep />
      <StatusItem label="Auto" value={String(autoCount)} />
      <StatusSep />
      <StatusItem label="Manual" value={String(manualCount)} />
      {editedCount > 0 && <>
        <StatusSep />
        <StatusItem label="Edited" value={String(editedCount)} highlight />
      </>}
      <StatusSep />
      <StatusItem label="Zoom" value={`${Math.round(zoom * 100)}%`} />
      {gridSnap && <>
        <StatusSep />
        <StatusItem label="Grid" value="ON" highlight />
      </>}

      <div style={{ flex: 1 }} />

      <span style={{ fontSize: 10, color: "#2d3748", fontWeight: 500 }}>
        Balloon Editor · RFQ Agent
      </span>

      <StatusSep />
      <span style={{ fontSize: 10, color: "#1e293b" }}>v1.1</span>
    </div>
  );
}

function StatusItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, padding: "0 8px" }}>
      <span style={{ color: "#2d3748" }}>{label}:</span>
      <span style={{ color: highlight ? "#f59e0b" : "#64748b", fontWeight: highlight ? 600 : 400 }}>
        {value}
      </span>
    </span>
  );
}

function StatusSep() {
  return <div style={{ width: 1, height: 12, background: "#1a2235", flexShrink: 0 }} />;
}
