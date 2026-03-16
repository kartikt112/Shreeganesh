import { useState } from "react";
import { useBalloonStore } from "../store/balloonStore";
import { MetadataPanel } from "./MetadataPanel";
import { Search, Plus, Filter, ChevronDown, ChevronUp, Circle } from "lucide-react";

interface SidebarProps {
  onEditBalloon: (id: string) => void;
}

const S = {
  root: {
    width: 300,
    borderLeft: "1px solid #1a2235",
    display: "flex",
    flexDirection: "column" as const,
    background: "#0d1117",
    overflow: "hidden",
    fontFamily: "Inter, -apple-system, sans-serif",
  },
  header: {
    padding: "12px 14px 10px",
    borderBottom: "1px solid #1a2235",
    background: "#0d1117",
    flexShrink: 0,
  },
  titleRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    color: "#e2e8f0",
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  countBadge: {
    fontSize: 10,
    fontWeight: 700,
    padding: "2px 7px",
    borderRadius: 9999,
    background: "rgba(59,130,246,0.15)",
    color: "#60a5fa",
    border: "1px solid rgba(59,130,246,0.2)",
  },
  addBtn: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "4px 10px",
    borderRadius: 6,
    background: "linear-gradient(135deg, #3b82f6, #6366f1)",
    color: "white",
    border: "none",
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 600,
    fontFamily: "inherit",
    boxShadow: "0 2px 6px rgba(59,130,246,0.25)",
  },
  searchWrap: {
    display: "flex",
    alignItems: "center",
    gap: 7,
    background: "#161b25",
    border: "1px solid #1a2235",
    borderRadius: 8,
    padding: "6px 10px",
    marginBottom: 8,
  },
  searchInput: {
    flex: 1,
    background: "none",
    border: "none",
    outline: "none",
    color: "#e2e8f0",
    fontSize: 12,
    fontFamily: "inherit",
  },
  filterRow: {
    display: "flex",
    gap: 6,
    alignItems: "center",
    fontSize: 11,
    color: "#64748b",
  },
  filterLabel: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    cursor: "pointer",
    padding: "2px 8px",
    borderRadius: 5,
    border: "1px solid transparent",
    transition: "all 0.15s",
    userSelect: "none" as const,
  },
  list: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "8px 0",
  },
  footer: {
    borderTop: "1px solid #1a2235",
    background: "#0d1117",
    flexShrink: 0,
  },
  footerToggle: {
    width: "100%",
    padding: "10px 14px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: 12,
    color: "#60a5fa",
    fontWeight: 500,
    textAlign: "left" as const,
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontFamily: "inherit",
    transition: "background 0.15s",
  },
};

function ConfidenceDot({ value }: { value?: number }) {
  const color = value === undefined ? "#334155"
    : value < 0.5 ? "#ef4444"
    : value < 0.75 ? "#f59e0b"
    : "#10b981";
  return (
    <div
      style={{ width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0 }}
      title={`Confidence: ${value !== undefined ? Math.round(value * 100) + "%" : "N/A"}`}
    />
  );
}

function FeatureBadge({ children, color }: { children: React.ReactNode; color: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    blue:   { bg: "rgba(59,130,246,0.1)",  text: "#60a5fa" },
    amber:  { bg: "rgba(245,158,11,0.1)",  text: "#fbbf24" },
    green:  { bg: "rgba(16,185,129,0.1)",  text: "#34d399" },
    purple: { bg: "rgba(139,92,246,0.1)",  text: "#a78bfa" },
    gray:   { bg: "rgba(100,116,139,0.1)", text: "#94a3b8" },
  };
  const c = colors[color] || colors.gray;
  return (
    <span style={{
      fontSize: 9, fontWeight: 600, padding: "1px 5px",
      borderRadius: 4, background: c.bg, color: c.text,
      textTransform: "uppercase", letterSpacing: "0.04em",
    }}>
      {children}
    </span>
  );
}

export function Sidebar({ onEditBalloon }: SidebarProps) {
  const { balloons, metadata, selectedId, setSelectedId, setMode } = useBalloonStore();
  const [filter, setFilter] = useState("");
  const [onlyEdited, setOnlyEdited] = useState(false);
  const [onlyManual, setOnlyManual] = useState(false);
  const [showMetadata, setShowMetadata] = useState(false);

  const sorted = [...balloons].sort((a, b) => a.feature.balloon_no - b.feature.balloon_no);

  const filtered = sorted.filter((b) => {
    if (onlyEdited && !b.feature.edited) return false;
    if (onlyManual && b.feature.source !== "manual") return false;
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      b.feature.balloon_no.toString().includes(q) ||
      (b.feature.specification || "").toLowerCase().includes(q) ||
      (b.feature.feature_type || "").toLowerCase().includes(q) ||
      (b.feature.description || "").toLowerCase().includes(q)
    );
  });

  const typeColorMap: Record<string, string> = {
    DIAMETER: "blue", RADIUS: "blue", LENGTH: "blue", WIDTH: "blue",
    ANGLE: "amber", THREAD: "amber",
    GD_T: "purple", SURFACE_FINISH: "purple",
    NOTE: "gray", TOLERANCE: "green",
    OTHER: "gray",
  };

  return (
    <div style={S.root}>
      {/* Header */}
      <div style={S.header}>
        <div style={S.titleRow}>
          <div style={S.title}>
            <Circle size={12} style={{ color: "#3b82f6" }} />
            Balloons
            <span style={S.countBadge}>{balloons.length}</span>
          </div>
          <button style={S.addBtn} onClick={() => setMode("add")}>
            <Plus size={12} /> Add
          </button>
        </div>

        {/* Search */}
        <div style={S.searchWrap}>
          <Search size={12} style={{ color: "#4a5568", flexShrink: 0 }} />
          <input
            type="text"
            placeholder="Search #, spec, type…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={S.searchInput}
          />
        </div>

        {/* Filters */}
        <div style={S.filterRow}>
          <Filter size={11} />
          <label
            style={{
              ...S.filterLabel,
              borderColor: onlyEdited ? "rgba(59,130,246,0.3)" : "transparent",
              background: onlyEdited ? "rgba(59,130,246,0.08)" : "transparent",
              color: onlyEdited ? "#60a5fa" : "#64748b",
            }}
          >
            <input
              type="checkbox"
              checked={onlyEdited}
              onChange={(e) => setOnlyEdited(e.target.checked)}
              style={{ display: "none" }}
            />
            Edited only
          </label>
          <label
            style={{
              ...S.filterLabel,
              borderColor: onlyManual ? "rgba(16,185,129,0.3)" : "transparent",
              background: onlyManual ? "rgba(16,185,129,0.08)" : "transparent",
              color: onlyManual ? "#34d399" : "#64748b",
            }}
          >
            <input
              type="checkbox"
              checked={onlyManual}
              onChange={(e) => setOnlyManual(e.target.checked)}
              style={{ display: "none" }}
            />
            Manual only
          </label>
          {filtered.length !== balloons.length && (
            <span style={{ marginLeft: "auto", color: "#60a5fa", fontWeight: 600 }}>
              {filtered.length}/{balloons.length}
            </span>
          )}
        </div>
      </div>

      {/* Feature list */}
      <div style={S.list}>
        {filtered.length === 0 && (
          <div style={{ padding: "32px 14px", textAlign: "center", color: "#4a5568", fontSize: 12 }}>
            {balloons.length === 0 ? "No balloons yet. Use Add mode to place one." : "No balloons match the filter."}
          </div>
        )}
        {filtered.map((b) => {
          const isSelected = selectedId === b.id;
          return (
            <div
              key={b.id}
              onClick={() => setSelectedId(b.id)}
              onDoubleClick={() => onEditBalloon(b.id)}
              style={{
                padding: "9px 14px",
                borderBottom: "1px solid #0d1117",
                cursor: "pointer",
                background: isSelected
                  ? "rgba(59,130,246,0.1)"
                  : "transparent",
                borderLeft: `3px solid ${isSelected ? "#3b82f6" : "transparent"}`,
                display: "flex",
                alignItems: "center",
                gap: 10,
                transition: "all 0.12s",
              }}
              onMouseEnter={(e) => {
                if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.03)";
              }}
              onMouseLeave={(e) => {
                if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "transparent";
              }}
            >
              {/* Balloon circle */}
              <div style={{
                width: 28, height: 28,
                borderRadius: "50%",
                background: isSelected ? "rgba(59,130,246,0.2)" : "rgba(255,255,255,0.05)",
                border: `2px solid ${isSelected ? "#3b82f6" : "#1e293b"}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 700,
                color: isSelected ? "#60a5fa" : "#94a3b8",
                flexShrink: 0,
                transition: "all 0.12s",
              }}>
                {b.feature.balloon_no}
              </div>

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 12, fontWeight: 600,
                  color: isSelected ? "#e2e8f0" : "#cbd5e1",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  fontFamily: "'JetBrains Mono', monospace",
                  marginBottom: 2,
                }}>
                  {b.feature.specification || <span style={{ color: "#4a5568", fontStyle: "italic" }}>empty</span>}
                </div>
                <div style={{ fontSize: 10, color: "#4a5568", display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                  <span>{b.feature.description || b.feature.feature_type}</span>
                </div>
              </div>

              {/* Badges */}
              <div style={{ display: "flex", alignItems: "center", gap: 3, flexShrink: 0 }}>
                <FeatureBadge color={typeColorMap[b.feature.feature_type] || "gray"}>
                  {b.feature.feature_type?.slice(0, 4) || "—"}
                </FeatureBadge>
                {b.feature.edited && <FeatureBadge color="amber">edited</FeatureBadge>}
                {b.feature.source === "manual" && <FeatureBadge color="green">manual</FeatureBadge>}
                <ConfidenceDot value={b.feature.confidence} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Metadata footer */}
      <div style={S.footer}>
        <button
          style={S.footerToggle}
          onClick={() => setShowMetadata(!showMetadata)}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.04)"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
        >
          {showMetadata ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
          Manufacturing Metadata
        </button>
        {showMetadata && (
          <div style={{ maxHeight: 220, overflowY: "auto", background: "#0a0d14" }}>
            <MetadataPanel metadata={metadata} />
          </div>
        )}
      </div>
    </div>
  );
}
