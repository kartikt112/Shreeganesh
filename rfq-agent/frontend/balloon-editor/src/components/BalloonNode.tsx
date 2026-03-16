import { memo, useRef } from "react";
import { Group, Circle, Text, Line } from "react-konva";
import Konva from "konva";
import type { BalloonState } from "../types/feature";

interface BalloonNodeProps {
  balloon: BalloonState;
  onDragEnd: (id: string, x: number, y: number) => void;
  onAnchorDragEnd: (id: string, anchorX: number, anchorY: number) => void;
  onResize: (id: string, radius: number) => void;
  onClick: (id: string) => void;
  onDblClick: (id: string) => void;
  leaderStyle?: "straight" | "angled" | "curved";
}

const DARK_BLUE = "#1F4E79";
const LIGHT_BLUE = "#E6F0FA";
const SELECTED_STROKE = "#FF6600";

function BalloonNodeComponent({
  balloon,
  onDragEnd,
  onAnchorDragEnd,
  onResize,
  onClick,
  onDblClick,
  leaderStyle = "straight",
}: BalloonNodeProps) {
  const { id, feature, x, y, anchorX, anchorY, selected, radius } = balloon;
  const lineRef = useRef<Konva.Line>(null);
  const anchorRef = useRef<Konva.Circle>(null);
  const circleRef = useRef<Konva.Circle>(null);
  const textRef = useRef<Konva.Text>(null);
  const resizeHandleRef = useRef<Konva.Circle>(null);

  // Offset from balloon to anchor (stays constant during balloon drag)
  const offsetX = anchorX - x;
  const offsetY = anchorY - y;

  const computeLeaderPoints = (
    bx: number,
    by: number,
    ax: number,
    ay: number
  ): number[] => {
    if (leaderStyle === "angled") {
      const midX = (ax + bx) / 2;
      return [ax, ay, midX, ay, midX, by, bx, by];
    }
    return [ax, ay, bx, by];
  };

  const fontSize = Math.max(8, Math.round(radius * 0.78));

  return (
    <Group>
      {/* Leader line — connects anchor to balloon */}
      <Line
        ref={lineRef}
        points={computeLeaderPoints(x, y, anchorX, anchorY)}
        stroke={DARK_BLUE}
        strokeWidth={1.5}
      />

      {/* Draggable balloon group */}
      <Group
        x={x}
        y={y}
        draggable
        onDragMove={(e) => {
          const newX = e.target.x();
          const newY = e.target.y();
          const newAnchorX = newX + offsetX;
          const newAnchorY = newY + offsetY;
          if (lineRef.current) {
            lineRef.current.points(
              computeLeaderPoints(newX, newY, newAnchorX, newAnchorY)
            );
          }
          if (anchorRef.current) {
            anchorRef.current.x(newAnchorX);
            anchorRef.current.y(newAnchorY);
          }
          // Move resize handle with balloon
          if (resizeHandleRef.current) {
            resizeHandleRef.current.x(newX + radius);
            resizeHandleRef.current.y(newY);
          }
        }}
        onDragEnd={(e) => {
          onDragEnd(id, e.target.x(), e.target.y());
        }}
        onClick={() => onClick(id)}
        onDblClick={() => onDblClick(id)}
      >
        {/* Balloon circle */}
        <Circle
          ref={circleRef}
          radius={radius}
          fill={LIGHT_BLUE}
          stroke={selected ? SELECTED_STROKE : DARK_BLUE}
          strokeWidth={selected ? 3 : 2}
        />
        {/* Balloon number */}
        <Text
          ref={textRef}
          text={String(feature.balloon_no)}
          fontSize={fontSize}
          fontStyle="bold"
          fill={DARK_BLUE}
          align="center"
          verticalAlign="middle"
          width={radius * 2}
          height={radius * 2}
          offsetX={radius}
          offsetY={radius}
        />
      </Group>

      {/* Anchor dot — independently draggable for 360° leader line positioning */}
      <Circle
        ref={anchorRef}
        x={anchorX}
        y={anchorY}
        radius={selected ? 6 : 3}
        fill={selected ? SELECTED_STROKE : DARK_BLUE}
        stroke={selected ? DARK_BLUE : undefined}
        strokeWidth={selected ? 1 : 0}
        hitStrokeWidth={12}
        draggable
        onDragMove={(e) => {
          const newAX = e.target.x();
          const newAY = e.target.y();
          if (lineRef.current) {
            lineRef.current.points(computeLeaderPoints(x, y, newAX, newAY));
          }
        }}
        onDragEnd={(e) => {
          onAnchorDragEnd(id, e.target.x(), e.target.y());
        }}
        onMouseEnter={(e) => {
          const container = e.target.getStage()?.container();
          if (container) container.style.cursor = "move";
        }}
        onMouseLeave={(e) => {
          const container = e.target.getStage()?.container();
          if (container) container.style.cursor = "default";
        }}
      />

      {/* Resize handle — only visible when selected */}
      {selected && (
        <Circle
          ref={resizeHandleRef}
          x={x + radius}
          y={y}
          radius={5}
          fill="white"
          stroke={SELECTED_STROKE}
          strokeWidth={2}
          hitStrokeWidth={10}
          draggable
          onDragMove={(e) => {
            const handleX = e.target.x();
            const handleY = e.target.y();
            const newRadius = Math.max(
              10,
              Math.min(60, Math.sqrt((handleX - x) ** 2 + (handleY - y) ** 2))
            );
            // Update circle and text via refs for real-time feedback
            if (circleRef.current) {
              circleRef.current.radius(newRadius);
            }
            if (textRef.current) {
              const newFontSize = Math.max(8, Math.round(newRadius * 0.78));
              textRef.current.fontSize(newFontSize);
              textRef.current.width(newRadius * 2);
              textRef.current.height(newRadius * 2);
              textRef.current.offsetX(newRadius);
              textRef.current.offsetY(newRadius);
            }
          }}
          onDragEnd={(e) => {
            const handleX = e.target.x();
            const handleY = e.target.y();
            const newRadius = Math.max(
              10,
              Math.min(60, Math.sqrt((handleX - x) ** 2 + (handleY - y) ** 2))
            );
            onResize(id, Math.round(newRadius));
          }}
          onMouseEnter={(e) => {
            const container = e.target.getStage()?.container();
            if (container) container.style.cursor = "nwse-resize";
          }}
          onMouseLeave={(e) => {
            const container = e.target.getStage()?.container();
            if (container) container.style.cursor = "default";
          }}
        />
      )}
    </Group>
  );
}

export const BalloonNode = memo(BalloonNodeComponent, (prev, next) => {
  // Re-render only when this balloon's own state or leader style changes
  const bPrev = prev.balloon;
  const bNext = next.balloon;
  return (
    bPrev.id === bNext.id &&
    bPrev.x === bNext.x &&
    bPrev.y === bNext.y &&
    bPrev.anchorX === bNext.anchorX &&
    bPrev.anchorY === bNext.anchorY &&
    bPrev.radius === bNext.radius &&
    bPrev.selected === bNext.selected &&
    bPrev.feature.balloon_no === bNext.feature.balloon_no &&
    prev.leaderStyle === next.leaderStyle
  );
});
