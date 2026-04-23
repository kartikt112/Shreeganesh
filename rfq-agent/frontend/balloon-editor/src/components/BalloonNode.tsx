import { memo, useRef } from "react";
import { Group, Circle, Text } from "react-konva";
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
  onClick,
  onDblClick,
}: BalloonNodeProps) {
  const { id, feature, x, y, selected, radius } = balloon;
  const circleRef = useRef<Konva.Circle>(null);
  const textRef = useRef<Konva.Text>(null);

  const fontSize = Math.max(8, Math.round(radius * 0.78));

  return (
    <Group
      x={x}
      y={y}
      draggable
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
  );
}

export const BalloonNode = memo(BalloonNodeComponent, (prev, next) => {
  const bPrev = prev.balloon;
  const bNext = next.balloon;
  return (
    bPrev.id === bNext.id &&
    bPrev.x === bNext.x &&
    bPrev.y === bNext.y &&
    bPrev.radius === bNext.radius &&
    bPrev.selected === bNext.selected &&
    bPrev.feature.balloon_no === bNext.feature.balloon_no
  );
});
