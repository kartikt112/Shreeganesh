import { useRef, useEffect, useState, useCallback } from "react";
import { Stage, Layer, Image as KonvaImage } from "react-konva";
import Konva from "konva";
import { BalloonNode } from "./BalloonNode";
import { useBalloonStore } from "../store/balloonStore";
import type { Feature, FeatureType } from "../types/feature";

interface CanvasProps {
  onBalloonSelect: (id: string | null) => void;
  onBalloonDblClick: (id: string) => void;
  stageRef: React.RefObject<Konva.Stage | null>;
}

export function Canvas({ onBalloonSelect, onBalloonDblClick, stageRef }: CanvasProps) {
  const {
    balloons,
    selectedId,
    mode,
    zoom,
    imageUrl,
    imageWidth,
    imageHeight,
    moveBalloon,
    moveAnchor,
    resizeBalloon,
    setSelectedId,
    addBalloon,
    swapFirstId,
    swapBalloons,
    setMode,
  } = useBalloonStore();

  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });

  // ── Pan state: spacebar + drag or middle-mouse drag ──
  const [isPanning, setIsPanning] = useState(false);
  const [spaceDown, setSpaceDown] = useState(false);
  const panStart = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);

  // Track spacebar for pan mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && !e.repeat && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setSpaceDown(true);
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        setSpaceDown(false);
        setIsPanning(false);
        panStart.current = null;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, []);

  // Pan handlers on the container div
  const handlePanMouseDown = useCallback(
    (e: React.MouseEvent) => {
      // Middle mouse button (button=1) or spacebar + left click
      if (e.button === 1 || (spaceDown && e.button === 0)) {
        e.preventDefault();
        const container = containerRef.current;
        if (!container) return;
        setIsPanning(true);
        panStart.current = {
          x: e.clientX,
          y: e.clientY,
          scrollLeft: container.scrollLeft,
          scrollTop: container.scrollTop,
        };
      }
    },
    [spaceDown]
  );

  const handlePanMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning || !panStart.current || !containerRef.current) return;
      e.preventDefault();
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      containerRef.current.scrollLeft = panStart.current.scrollLeft - dx;
      containerRef.current.scrollTop = panStart.current.scrollTop - dy;
    },
    [isPanning]
  );

  const handlePanMouseUp = useCallback(() => {
    setIsPanning(false);
    panStart.current = null;
  }, []);

  // Load drawing image (stable instance, no dependency on balloons/zoom)
  useEffect(() => {
    if (!imageUrl) return;
    const img = new window.Image();
    img.crossOrigin = "anonymous";
    img.onload = () => setImage(img);
    img.src = imageUrl;
  }, [imageUrl]);

  // Container resize
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setContainerSize({ width, height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      // Don't handle clicks while panning
      if (spaceDown || isPanning) return;

      // Check if clicking on empty canvas
      const clickedOnEmpty = e.target === e.target.getStage();
      if (!clickedOnEmpty && e.target.getParent()?.getClassName() !== "Layer") {
        return; // Clicked on a balloon, handled by balloon's onClick
      }

      if (mode === "add") {
        const stage = e.target.getStage();
        if (!stage) return;
        const pos = stage.getPointerPosition();
        if (!pos) return;

        const newFeature: Feature = {
          balloon_no: 0, // Will be auto-assigned
          specification: "",
          description: "",
          feature_type: "OTHER" as FeatureType,
          source: "manual",
          confidence: 1.0,
        };
        addBalloon(newFeature, pos.x / zoom, pos.y / zoom);
        onBalloonDblClick(""); // Trigger edit popover for the new balloon
      } else {
        setSelectedId(null);
        onBalloonSelect(null);
      }
    },
    [mode, zoom, spaceDown, isPanning, addBalloon, setSelectedId, onBalloonSelect, onBalloonDblClick]
  );

  const handleBalloonClick = useCallback(
    (id: string) => {
      if (mode === "swap") {
        const store = useBalloonStore.getState();
        if (!store.swapFirstId) {
          useBalloonStore.setState({ swapFirstId: id });
        } else {
          swapBalloons(store.swapFirstId, id);
        }
        return;
      }
      setSelectedId(id);
      onBalloonSelect(id);
    },
    [mode, swapBalloons, setSelectedId, onBalloonSelect]
  );

  const handleWheel = useCallback(
    (e: Konva.KonvaEventObject<WheelEvent>) => {
      e.evt.preventDefault();
      const scaleBy = 1.1;
      const store = useBalloonStore.getState();
      const newZoom =
        e.evt.deltaY < 0
          ? store.zoom * scaleBy
          : store.zoom / scaleBy;
      useBalloonStore.getState().setZoom(newZoom);
    },
    []
  );

  const stageWidth = imageWidth || containerSize.width;
  const stageHeight = imageHeight || containerSize.height;

  return (
    <div
      ref={containerRef}
      data-canvas-container
      onMouseDown={handlePanMouseDown}
      onMouseMove={handlePanMouseMove}
      onMouseUp={handlePanMouseUp}
      onMouseLeave={handlePanMouseUp}
      style={{
        flex: 1,
        overflow: "auto",
        background: "#f0f0f0",
        cursor:
          isPanning
            ? "grabbing"
            : spaceDown
            ? "grab"
            : mode === "add"
            ? "crosshair"
            : mode === "swap"
            ? "pointer"
            : "default",
      }}
    >
      <Stage
        ref={stageRef}
        width={stageWidth * zoom}
        height={stageHeight * zoom}
        scaleX={zoom}
        scaleY={zoom}
        onClick={handleStageClick}
        onWheel={handleWheel}
      >
        {/* Static background layer */}
        <Layer listening={false}>
          {image && (
            <KonvaImage
              image={image}
              width={imageWidth || image.width}
              height={imageHeight || image.height}
            />
          )}
        </Layer>

        {/* Interactive balloons layer */}
        <Layer>
          {balloons.map((b) => (
            <BalloonNode
              key={b.id}
              balloon={b}
              onDragEnd={moveBalloon}
              onAnchorDragEnd={moveAnchor}
              onResize={resizeBalloon}
              onClick={handleBalloonClick}
              onDblClick={onBalloonDblClick}
            />
          ))}
        </Layer>
      </Stage>
    </div>
  );
}
