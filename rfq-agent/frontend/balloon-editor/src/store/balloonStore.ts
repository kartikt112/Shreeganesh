import { create } from "zustand";
import { produce } from "immer";
import type { Feature, BalloonState, EditorMode } from "../types/feature";
import type { ManufacturingMetadata } from "../types/metadata";
import { undoMiddleware } from "./undoMiddleware";

interface BalloonStoreState {
  balloons: BalloonState[];
  metadata: ManufacturingMetadata | null;
  selectedId: string | null;
  mode: EditorMode;
  swapFirstId: string | null;
  zoom: number;
  gridSnap: boolean;
  imageUrl: string | null;
  imageWidth: number;
  imageHeight: number;
}

interface BalloonStoreActions {
  // Data loading
  loadData: (
    features: Feature[],
    metadata: ManufacturingMetadata | null,
    imgW: number,
    imgH: number
  ) => void;
  setImageUrl: (url: string) => void;

  // Selection & mode
  setSelectedId: (id: string | null) => void;
  setMode: (mode: EditorMode) => void;

  // Balloon operations
  moveBalloon: (id: string, x: number, y: number) => void;
  moveAnchor: (id: string, anchorX: number, anchorY: number) => void;
  resizeBalloon: (id: string, radius: number) => void;
  renumberBalloon: (id: string, newNo: number) => void;
  swapBalloons: (id1: string, id2: string) => void;
  editFeature: (id: string, updates: Partial<Feature>) => void;
  addBalloon: (feature: Feature, x: number, y: number) => void;
  deleteBalloon: (id: string) => void;

  // View controls
  setZoom: (zoom: number) => void;
  toggleGridSnap: () => void;

  // Export helpers
  getExportData: () => {
    features: Feature[];
    manufacturing_metadata: ManufacturingMetadata | null;
  };
}

type StoreState = BalloonStoreState & BalloonStoreActions;

const featureToBalloon = (
  f: Feature,
  imgW: number,
  imgH: number
): BalloonState => {
  const box = f.box_2d;
  const ed = f as Record<string, unknown>;

  // If editor layout was saved, restore exact positions
  if (typeof ed._editor_x === "number") {
    return {
      id: `balloon-${f.balloon_no}-${Date.now()}`,
      feature: { ...f },
      x: ed._editor_x as number,
      y: ed._editor_y as number,
      anchorX: ed._editor_anchorX as number,
      anchorY: ed._editor_anchorY as number,
      selected: false,
      radius: (ed._editor_radius as number) || 18,
    };
  }

  // All coordinates from the backend (box_2d, balloon_position) are
  // already in pixel space — no scaling needed.

  // Radius proportional to image — visible at any zoom level
  const diag = Math.sqrt(imgW * imgW + imgH * imgH);
  const defaultRadius = Math.min(45, Math.max(20, diag / 120));
  // Max leader line length — keep balloons close to features
  const maxLeaderLen = diag * 0.12;

  // Compute anchor from box_2d [ymin, xmin, ymax, xmax] in pixel coords
  let anchorX = imgW * 0.1;
  let anchorY = imgH * 0.1;
  let boxCenterX = anchorX;
  let boxCenterY = anchorY;

  if (box && box.length === 4) {
    const [ymin, xmin, ymax, xmax] = box;
    boxCenterX = (xmin + xmax) / 2;
    boxCenterY = (ymin + ymax) / 2;
    anchorX = boxCenterX;
    anchorY = boxCenterY;
  }

  // Use backend balloon_position if it produces a reasonable leader line
  const bp = ed.balloon_position as number[] | undefined;
  const rawRadius = (ed.balloon_radius as number) || 0;
  const br = rawRadius >= 14 ? Math.max(rawRadius, defaultRadius) : defaultRadius;

  if (bp && bp.length === 2) {
    let bx = bp[0];
    let by = bp[1];

    // Compute anchor as nearest point on box_2d edge to balloon
    if (box && box.length === 4) {
      const [ymin, xmin, ymax, xmax] = box;
      anchorX = Math.max(xmin, Math.min(xmax, bx));
      anchorY = Math.max(ymin, Math.min(ymax, by));
    }

    const leaderLen = Math.sqrt((bx - anchorX) ** 2 + (by - anchorY) ** 2);

    // If leader line is reasonable, use the backend position
    if (leaderLen <= maxLeaderLen && leaderLen > 0) {
      return {
        id: `balloon-${f.balloon_no}-${Date.now()}`,
        feature: { ...f },
        x: bx,
        y: by,
        anchorX,
        anchorY,
        selected: false,
        radius: br,
      };
    }
    // Otherwise fall through — reposition balloon close to the anchor
  }

  // Place balloon at a short offset from anchor (alternating directions
  // based on balloon number to reduce overlaps)
  const offset = br + 20;
  const bno = f.balloon_no || 1;
  // Cycle through 8 directions to spread balloons around their anchors
  const angle = ((bno - 1) % 8) * (Math.PI / 4);
  let balloonX = anchorX + Math.cos(angle) * offset;
  let balloonY = anchorY + Math.sin(angle) * offset;

  // Clamp within image bounds
  balloonX = Math.max(br, Math.min(imgW - br, balloonX));
  balloonY = Math.max(br, Math.min(imgH - br, balloonY));

  return {
    id: `balloon-${f.balloon_no}-${Date.now()}`,
    feature: { ...f },
    x: balloonX,
    y: balloonY,
    anchorX,
    anchorY,
    selected: false,
    radius: br,
  };
};

export const useBalloonStore = create<StoreState>()(
  undoMiddleware(
    (set, get) => ({
      // State
      balloons: [],
      metadata: null,
      selectedId: null,
      mode: "select" as EditorMode,
      swapFirstId: null,
      zoom: 1,
      gridSnap: false,
      imageUrl: null,
      imageWidth: 0,
      imageHeight: 0,

      // Data loading
      loadData: (features, metadata, imgW, imgH) => {
        const balloons = features.map((f) => featureToBalloon(f, imgW, imgH));
        set({ balloons, metadata, imageWidth: imgW, imageHeight: imgH });
      },

      setImageUrl: (url) => set({ imageUrl: url }),

      // Selection
      setSelectedId: (id) =>
        set(
          produce((state: BalloonStoreState) => {
            state.selectedId = id;
            state.balloons.forEach((b) => {
              b.selected = b.id === id;
            });
          })
        ),

      setMode: (mode) =>
        set({ mode, swapFirstId: null, selectedId: null }),

      // Balloon operations
      moveBalloon: (id, x, y) =>
        set(
          produce((state: BalloonStoreState) => {
            const b = state.balloons.find((b) => b.id === id);
            if (b) {
              const dx = x - b.x;
              const dy = y - b.y;
              if (state.gridSnap) {
                b.x = Math.round(x / 10) * 10;
                b.y = Math.round(y / 10) * 10;
              } else {
                b.x = x;
                b.y = y;
              }
              // Move anchor with the balloon so the leader line doesn't stretch
              b.anchorX += dx;
              b.anchorY += dy;
            }
          })
        ),

      moveAnchor: (id, anchorX, anchorY) =>
        set(
          produce((state: BalloonStoreState) => {
            const b = state.balloons.find((b) => b.id === id);
            if (b) {
              if (state.gridSnap) {
                b.anchorX = Math.round(anchorX / 10) * 10;
                b.anchorY = Math.round(anchorY / 10) * 10;
              } else {
                b.anchorX = anchorX;
                b.anchorY = anchorY;
              }
            }
          })
        ),

      resizeBalloon: (id, radius) =>
        set(
          produce((state: BalloonStoreState) => {
            const b = state.balloons.find((b) => b.id === id);
            if (b) {
              b.radius = Math.max(10, Math.min(60, radius));
            }
          })
        ),

      renumberBalloon: (id, newNo) => {
        const state = get();
        const hasDuplicate = state.balloons.some(
          (b) => b.id !== id && b.feature.balloon_no === newNo
        );
        if (hasDuplicate) {
          console.warn(`Balloon #${newNo} already exists`);
          return;
        }
        set(
          produce((state: BalloonStoreState) => {
            const b = state.balloons.find((b) => b.id === id);
            if (b) {
              b.feature.balloon_no = newNo;
              b.feature.edited = true;
            }
          })
        );
      },

      swapBalloons: (id1, id2) =>
        set(
          produce((state: BalloonStoreState) => {
            const b1 = state.balloons.find((b) => b.id === id1);
            const b2 = state.balloons.find((b) => b.id === id2);
            if (b1 && b2) {
              const tempNo = b1.feature.balloon_no;
              b1.feature.balloon_no = b2.feature.balloon_no;
              b2.feature.balloon_no = tempNo;
              b1.feature.edited = true;
              b2.feature.edited = true;
            }
            state.swapFirstId = null;
            state.mode = "select";
          })
        ),

      editFeature: (id, updates) =>
        set(
          produce((state: BalloonStoreState) => {
            const b = state.balloons.find((b) => b.id === id);
            if (b) {
              Object.assign(b.feature, updates);
              b.feature.edited = true;
            }
          })
        ),

      addBalloon: (feature, x, y) =>
        set(
          produce((state: BalloonStoreState) => {
            const maxNo = Math.max(
              0,
              ...state.balloons.map((b) => b.feature.balloon_no)
            );
            feature.balloon_no = maxNo + 1;
            feature.source = "manual";
            state.balloons.push({
              id: `balloon-${feature.balloon_no}-${Date.now()}`,
              feature,
              x,
              y,
              anchorX: x,
              anchorY: y,
              selected: false,
              radius: 18,
            });
            state.mode = "select";
          })
        ),

      deleteBalloon: (id) =>
        set(
          produce((state: BalloonStoreState) => {
            state.balloons = state.balloons.filter((b) => b.id !== id);
            if (state.selectedId === id) {
              state.selectedId = null;
            }
          })
        ),

      // View
      setZoom: (zoom) =>
        set({ zoom: Math.max(0.25, Math.min(4, zoom)) }),

      toggleGridSnap: () =>
        set((state) => ({ gridSnap: !state.gridSnap })),

      // Export
      getExportData: () => {
        const state = get();
        const features = state.balloons.map((b) => ({
          ...b.feature,
          box_2d: [b.anchorY - 10, b.anchorX - 10, b.anchorY + 10, b.anchorX + 10],
          // Editor layout — restored when reopening the editor
          _editor_x: b.x,
          _editor_y: b.y,
          _editor_anchorX: b.anchorX,
          _editor_anchorY: b.anchorY,
          _editor_radius: b.radius,
        }));
        return {
          features,
          manufacturing_metadata: state.metadata,
        };
      },
    }),
    ["balloons", "metadata", "selectedId"]
  )
);
