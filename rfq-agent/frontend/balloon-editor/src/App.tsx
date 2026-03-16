import { useState, useRef, useCallback, useEffect } from "react";
import Konva from "konva";
import { Canvas } from "./components/Canvas";
import { Sidebar } from "./components/Sidebar";
import { Toolbar } from "./components/Toolbar";
import { EditPopover } from "./components/EditPopover";
import { StatusBar } from "./components/StatusBar";
import { useBalloonStore } from "./store/balloonStore";
import { exportPNG, exportJSON, exportCSV } from "./utils/exportUtils";
import {
  loadFromFile,
  loadFromApiEndpoint,
  parseFromText,
} from "./utils/dataLoader";
import { saveToServer } from "./utils/saveToServer";

function App() {
  const stageRef = useRef<Konva.Stage | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");

  // Parse URL params for API mode
  const [apiParams] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const rfqId = params.get("rfq_id");
    const apiBase = params.get("api") || "http://localhost:8000";
    return rfqId ? { rfqId: parseInt(rfqId), apiBase } : null;
  });

  const {
    loadData,
    imageUrl: storeImageUrl,
    setImageUrl,
    setMode,
    deleteBalloon,
    selectedId,
    undo,
    redo,
    setZoom,
    zoom,
    toggleGridSnap,
  } = useBalloonStore();

  // Detect URL params and set loading immediately to avoid flash of empty state
  const [hasUrlParams] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return !!(params.get("rfq_id") || (params.get("image") && params.get("data")));
  });

  // Load from URL parameters on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const rfqId = params.get("rfq_id");
    const apiBase = params.get("api") || "http://localhost:8000";
    const imageParam = params.get("image");
    const dataParam = params.get("data");

    if (rfqId) {
      loadFromApi(parseInt(rfqId), apiBase);
    } else if (imageParam && dataParam) {
      loadFromUrls(imageParam, dataParam);
    }
  }, []);

  const loadFromApi = async (rfqId: number, apiBase: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await loadFromApiEndpoint(rfqId, apiBase);
      const imgUrl = data.image_path
        ? `${apiBase}${data.image_path}`
        : "";

      if (imgUrl) {
        const img = new window.Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          loadData(
            data.features,
            data.manufacturing_metadata,
            img.width,
            img.height
          );
          setImageUrl(imgUrl);
          setLoading(false);
        };
        img.onerror = () => {
          setError("Failed to load drawing image");
          setLoading(false);
        };
        img.src = imgUrl;
      } else {
        setError("No drawing image available for this RFQ");
        setLoading(false);
      }
    } catch (err) {
      setError(String(err));
      setLoading(false);
    }
  };

  const loadFromUrls = async (imageUrl: string, dataUrl: string) => {
    setLoading(true);
    try {
      const resp = await fetch(dataUrl);
      const data = await resp.json();
      const img = new window.Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        loadData(
          data.features || data,
          data.manufacturing_metadata || null,
          img.width,
          img.height
        );
        setImageUrl(imageUrl);
        setLoading(false);
      };
      img.src = imageUrl;
    } catch (err) {
      setError(String(err));
      setLoading(false);
    }
  };

  // File drop handlers
  const handleImageDrop = async (file: File) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      setImageUrl(url);
      useBalloonStore.setState({ imageWidth: img.width, imageHeight: img.height });
    };
    img.src = url;
  };

  const handleJsonDrop = async (file: File) => {
    try {
      const data = await loadFromFile(file);
      const store = useBalloonStore.getState();
      loadData(
        data.features,
        data.manufacturing_metadata,
        store.imageWidth || 800,
        store.imageHeight || 600
      );
    } catch (err) {
      setError(String(err));
    }
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files);
      for (const file of files) {
        if (file.type.startsWith("image/")) {
          handleImageDrop(file);
        } else if (file.name.endsWith(".json")) {
          handleJsonDrop(file);
        }
      }
    },
    [loadData, setImageUrl]
  );

  const handlePasteLoad = () => {
    try {
      const data = parseFromText(pasteText);
      const store = useBalloonStore.getState();
      loadData(
        data.features,
        data.manufacturing_metadata,
        store.imageWidth || 800,
        store.imageHeight || 600
      );
      setShowPaste(false);
      setPasteText("");
    } catch (err) {
      setError(String(err));
    }
  };

  // Listen for postMessage requests from parent (when embedded as iframe)
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === "get-editor-data") {
        const data = useBalloonStore.getState().getExportData();
        window.parent.postMessage(
          { type: "editor-data", features: data.features, manufacturing_metadata: data.manufacturing_metadata },
          "*"
        );
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }

      if (e.key === "a" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        setMode("add");
      } else if (e.key === "s" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        setMode("swap");
      } else if (e.key === "Escape") {
        setMode("select");
        setEditingId(null);
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
        e.preventDefault();
        deleteBalloon(selectedId);
      } else if (e.key === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (e.key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        redo();
      } else if (e.key === "=" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setZoom(zoom * 1.25);
      } else if (e.key === "-" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setZoom(zoom / 1.25);
      } else if (e.key === "0" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const state = useBalloonStore.getState();
        const container = document.querySelector('[data-canvas-container]');
        if (container && state.imageWidth && state.imageHeight) {
          const rect = container.getBoundingClientRect();
          const fitZoom = Math.min(rect.width / state.imageWidth, rect.height / state.imageHeight);
          setZoom(fitZoom);
        } else {
          setZoom(1);
        }
      } else if (e.key === "g") {
        e.preventDefault();
        toggleGridSnap();
      } else if (e.key === "s" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
        e.preventDefault();
        if (apiParams) handleSaveToServer();
      } else if (e.key === "e" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        handleExportPNG();
      } else if (e.key === "j" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        handleExportJSON();
      } else if (e.key === "c" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        handleExportCSV();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedId, zoom]);

  const handleExportPNG = () => {
    if (stageRef.current) {
      exportPNG(stageRef.current);
    }
  };

  const handleExportJSON = () => {
    const data = useBalloonStore.getState().getExportData();
    exportJSON(data.features, data.manufacturing_metadata);
  };

  const handleExportCSV = () => {
    const data = useBalloonStore.getState().getExportData();
    exportCSV(data.features);
  };

  const handleSaveToServer = async () => {
    if (!apiParams || !stageRef.current) return;
    setSaving(true);
    setError(null);
    try {
      const data = useBalloonStore.getState().getExportData();
      await saveToServer(
        apiParams.rfqId,
        apiParams.apiBase,
        data.features,
        data.manufacturing_metadata,
        stageRef.current
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  // Empty state — no image loaded yet
  if (!storeImageUrl && !loading && !hasUrlParams) {
    return (
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        style={{
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#080b12",
          fontFamily: "Inter, -apple-system, sans-serif",
        }}
      >
        <div style={{ marginBottom: 32, textAlign: "center" }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16,
            background: "linear-gradient(135deg, #3b82f6, #6366f1)",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 16px", boxShadow: "0 4px 24px rgba(59,130,246,0.3)",
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
            </svg>
          </div>
          <h1 style={{ color: "#e2e8f0", margin: "0 0 6px", fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em" }}>Balloon Editor</h1>
          <p style={{ color: "#4a5568", margin: 0, fontSize: 13 }}>Engineering drawing balloon annotation editor</p>
        </div>

        <div
          style={{
            border: "2px dashed #1a2235",
            borderRadius: 16,
            padding: "36px 56px",
            textAlign: "center",
            color: "#64748b",
            maxWidth: 480,
            width: "90%",
            background: "rgba(255,255,255,0.015)",
          }}
        >
          <p style={{ fontSize: 14, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>
            Drop drawing image + feature JSON here
          </p>
          <p style={{ fontSize: 12, color: "#4a5568", marginBottom: 20 }}>
            Or pass URL params: ?rfq_id=1&amp;api=http://localhost:8000
          </p>
          <button
            onClick={() => setShowPaste(true)}
            style={{
              padding: "8px 20px",
              background: "rgba(59,130,246,0.12)",
              border: "1px solid rgba(59,130,246,0.3)",
              borderRadius: 8, cursor: "pointer",
              color: "#60a5fa", fontSize: 13, fontWeight: 600, fontFamily: "inherit",
            }}
          >
            Paste JSON
          </button>
        </div>

        {showPaste && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, backdropFilter: "blur(4px)" }}>
            <div style={{ background: "#111722", border: "1px solid #1a2235", borderRadius: 16, padding: 24, width: 520, boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}>
              <h3 style={{ margin: "0 0 14px", color: "#e2e8f0", fontSize: 16, fontWeight: 600 }}>Paste Feature JSON</h3>
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder='{"features": [...], "manufacturing_metadata": {...}}'
                style={{ width: "100%", height: 200, border: "1px solid #1a2235", borderRadius: 8, padding: 10, fontFamily: "'JetBrains Mono', monospace", fontSize: 11, boxSizing: "border-box", background: "#0a0d14", color: "#94a3b8", outline: "none", resize: "vertical" }}
              />
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
                <button onClick={() => { setShowPaste(false); setPasteText(""); }}
                  style={{ padding: "7px 18px", background: "transparent", border: "1px solid #1a2235", borderRadius: 8, cursor: "pointer", color: "#94a3b8", fontFamily: "inherit", fontSize: 13 }}>
                  Cancel
                </button>
                <button onClick={handlePasteLoad}
                  style={{ padding: "7px 18px", background: "linear-gradient(135deg, #3b82f6, #6366f1)", border: "none", borderRadius: 8, cursor: "pointer", color: "white", fontFamily: "inherit", fontSize: 13, fontWeight: 600 }}>
                  Load
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 20, padding: "10px 18px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, color: "#f87171", fontSize: 13 }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  if (loading || (hasUrlParams && !storeImageUrl && !error)) {
    return (
      <div style={{ height: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#080b12", gap: 16, fontFamily: "Inter, sans-serif" }}>
        <div style={{ width: 44, height: 44, position: "relative" }}>
          <div style={{ position: "absolute", inset: 0, border: "2px solid #1a2235", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin 0.9s linear infinite" }} />
        </div>
        <p style={{ color: "#4a5568", fontSize: 13, margin: 0 }}>Loading drawing data…</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: "Inter, -apple-system, sans-serif",
        background: "#080b12",
      }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      <Toolbar
        onExportPNG={handleExportPNG}
        onExportJSON={handleExportJSON}
        onExportCSV={handleExportCSV}
        onSaveToServer={apiParams ? handleSaveToServer : undefined}
        saving={saving}
      />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <Canvas
          stageRef={stageRef}
          onBalloonSelect={() => {
            if (editingId) setEditingId(null);
          }}
          onBalloonDblClick={(id) => setEditingId(id)}
        />
        <Sidebar onEditBalloon={(id) => setEditingId(id)} />
      </div>

      <StatusBar />

      {editingId && (
        <EditPopover
          balloonId={editingId}
          onClose={() => setEditingId(null)}
        />
      )}

      {error && (
        <div
          style={{
            position: "fixed",
            bottom: 40,
            left: "50%",
            transform: "translateX(-50%)",
            padding: "10px 18px",
            background: "rgba(239,68,68,0.15)",
            border: "1px solid rgba(239,68,68,0.4)",
            backdropFilter: "blur(8px)",
            color: "#f87171",
            borderRadius: 10,
            fontSize: 13,
            fontWeight: 500,
            zIndex: 999,
            cursor: "pointer",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            fontFamily: "Inter, sans-serif",
          }}
          onClick={() => setError(null)}
        >
          ✕ {error}
        </div>
      )}
    </div>
  );
}

export default App;
