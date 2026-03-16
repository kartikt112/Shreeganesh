import {
  MousePointer2, Plus, ArrowLeftRight, Trash2,
  Undo2, Redo2, ZoomIn, ZoomOut, Maximize,
  Download, FileJson, FileSpreadsheet, Grid3X3,
  Save, Loader2, ChevronDown,
} from "lucide-react";
import { useBalloonStore } from "../store/balloonStore";
import type { EditorMode } from "../types/feature";

interface ToolbarProps {
  onExportPNG: () => void;
  onExportJSON: () => void;
  onExportCSV: () => void;
  onSaveToServer?: () => void;
  saving?: boolean;
}

const T_STYLES = {
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 2,
    padding: "6px 10px",
    background: "#0d1117",
    borderBottom: "1px solid #1a2235",
    flexWrap: "wrap" as const,
    minHeight: 46,
    userSelect: "none" as const,
  },
  divider: {
    width: 1,
    height: 22,
    background: "#1a2235",
    margin: "0 4px",
    flexShrink: 0 as const,
  },
  toolGroup: {
    display: "flex",
    alignItems: "center",
    gap: 2,
    background: "#161b25",
    borderRadius: 8,
    border: "1px solid #1a2235",
    padding: "2px 3px",
  },
};

function ToolBtn({
  icon, label, shortcut, active, disabled, onClick, danger
}: {
  icon: React.ReactNode;
  label: string;
  shortcut?: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={`${label}${shortcut ? `  (${shortcut})` : ""}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 5,
        padding: "4px 9px",
        border: active ? "1px solid rgba(59,130,246,0.5)" : "1px solid transparent",
        borderRadius: 6,
        background: active
          ? "rgba(59,130,246,0.15)"
          : danger
          ? "transparent"
          : "transparent",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.35 : 1,
        fontSize: 11,
        fontFamily: "Inter, -apple-system, sans-serif",
        fontWeight: 500,
        color: active
          ? "#60a5fa"
          : danger
          ? "#f87171"
          : "#94a3b8",
        transition: "all 0.15s",
        whiteSpace: "nowrap" as const,
        flexShrink: 0,
      }}
      onMouseEnter={(e) => {
        if (!disabled && !active) {
          (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.05)";
          (e.currentTarget as HTMLButtonElement).style.color = "#e2e8f0";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          (e.currentTarget as HTMLButtonElement).style.background = "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = danger ? "#f87171" : "#94a3b8";
        }
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export function Toolbar({ onExportPNG, onExportJSON, onExportCSV, onSaveToServer, saving }: ToolbarProps) {
  const {
    mode, zoom, gridSnap, selectedId,
    setMode, setZoom, toggleGridSnap,
    deleteBalloon, undo, redo, canUndo, canRedo,
    balloons,
  } = useBalloonStore();

  const handleDelete = () => { if (selectedId) deleteBalloon(selectedId); };

  const fitToView = () => {
    const state = useBalloonStore.getState();
    const container = document.querySelector("[data-canvas-container]");
    if (container && state.imageWidth && state.imageHeight) {
      const rect = container.getBoundingClientRect();
      const fitZoom = Math.min(rect.width / state.imageWidth, rect.height / state.imageHeight) * 0.96;
      setZoom(fitZoom);
    } else {
      setZoom(1);
    }
  };

  return (
    <div style={T_STYLES.toolbar}>

      {/* Mode tools */}
      <div style={T_STYLES.toolGroup}>
        <ToolBtn
          icon={<MousePointer2 size={14} />}
          label="Select"
          shortcut="Esc"
          active={mode === "select"}
          onClick={() => setMode("select")}
        />
        <ToolBtn
          icon={<Plus size={14} />}
          label="Add"
          shortcut="A"
          active={mode === "add"}
          onClick={() => setMode("add")}
        />
        <ToolBtn
          icon={<ArrowLeftRight size={14} />}
          label="Swap"
          shortcut="S"
          active={mode === "swap"}
          onClick={() => setMode("swap")}
        />
        <ToolBtn
          icon={<Trash2 size={14} />}
          label="Delete"
          shortcut="Del"
          disabled={!selectedId}
          onClick={handleDelete}
          danger
        />
      </div>

      <div style={T_STYLES.divider} />

      {/* Undo / Redo */}
      <div style={T_STYLES.toolGroup}>
        <ToolBtn icon={<Undo2 size={14} />} label="Undo" shortcut="⌘Z" onClick={() => undo()} disabled={!canUndo()} />
        <ToolBtn icon={<Redo2 size={14} />} label="Redo" shortcut="⌘⇧Z" onClick={() => redo()} disabled={!canRedo()} />
      </div>

      <div style={T_STYLES.divider} />

      {/* Zoom controls */}
      <div style={T_STYLES.toolGroup}>
        <ToolBtn icon={<ZoomOut size={14} />} label="Out" shortcut="⌘−" onClick={() => setZoom(zoom / 1.25)} />
        <div style={{
          padding: "4px 8px",
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          color: "#64748b",
          minWidth: 48,
          textAlign: "center",
          cursor: "pointer",
          borderRadius: 4,
          transition: "all 0.15s",
        }}
          onClick={fitToView}
          title="Reset to fit (Ctrl+0)"
        >
          {Math.round(zoom * 100)}%
        </div>
        <ToolBtn icon={<ZoomIn size={14} />} label="In" shortcut="⌘+" onClick={() => setZoom(zoom * 1.25)} />
        <ToolBtn icon={<Maximize size={14} />} label="Fit" shortcut="⌘0" onClick={fitToView} />
      </div>

      <div style={T_STYLES.divider} />

      {/* Grid snap */}
      <ToolBtn
        icon={<Grid3X3 size={14} />}
        label="Grid"
        shortcut="G"
        active={gridSnap}
        onClick={toggleGridSnap}
      />

      <div style={T_STYLES.divider} />

      {/* Export group */}
      <div style={T_STYLES.toolGroup}>
        <ToolBtn icon={<Download size={14} />} label="PNG" shortcut="⌘⇧E" onClick={onExportPNG} />
        <ToolBtn icon={<FileJson size={14} />} label="JSON" shortcut="⌘⇧J" onClick={onExportJSON} />
        <ToolBtn icon={<FileSpreadsheet size={14} />} label="CSV" shortcut="⌘⇧C" onClick={onExportCSV} />
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Balloon count pill */}
      <div style={{
        padding: "3px 10px",
        background: "rgba(59,130,246,0.1)",
        border: "1px solid rgba(59,130,246,0.2)",
        borderRadius: 9999,
        fontSize: 11,
        color: "#60a5fa",
        fontWeight: 600,
        flexShrink: 0,
      }}>
        {balloons.length} balloon{balloons.length !== 1 ? "s" : ""}
      </div>

      {/* Save to Server */}
      {onSaveToServer && (
        <button
          onClick={onSaveToServer}
          disabled={saving}
          title="Save features & image to server (Ctrl+S)"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 16px",
            border: "none",
            borderRadius: 8,
            background: saving
              ? "rgba(59,130,246,0.3)"
              : "linear-gradient(135deg, #3b82f6, #6366f1)",
            color: "white",
            cursor: saving ? "not-allowed" : "pointer",
            fontSize: 12,
            fontWeight: 600,
            fontFamily: "Inter, sans-serif",
            boxShadow: saving ? "none" : "0 2px 8px rgba(59,130,246,0.3)",
            transition: "all 0.18s",
            flexShrink: 0,
          }}
        >
          {saving ? <Loader2 size={13} style={{ animation: "spin 0.9s linear infinite" }} /> : <Save size={13} />}
          {saving ? "Saving…" : "Save to RFQ"}
        </button>
      )}
    </div>
  );
}
