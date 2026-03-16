export function snapToGrid(value: number, gridSize: number = 10): number {
  return Math.round(value / gridSize) * gridSize;
}

export function distance(
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
}

export function elbowLine(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number
): number[] {
  const midX = (fromX + toX) / 2;
  return [fromX, fromY, midX, fromY, midX, toY, toX, toY];
}

export function curvedLine(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number
): { x: number; y: number }[] {
  const midX = (fromX + toX) / 2;
  const cp1x = fromX + (midX - fromX) * 0.5;
  const cp2x = toX - (toX - midX) * 0.5;
  return [
    { x: fromX, y: fromY },
    { x: cp1x, y: fromY },
    { x: cp2x, y: toY },
    { x: toX, y: toY },
  ];
}

export function resolveOverlap(
  positions: { x: number; y: number }[],
  newX: number,
  newY: number,
  threshold: number = 40,
  offset: number = 60
): { x: number; y: number } {
  let x = newX;
  let y = newY;

  for (const pos of positions) {
    if (distance(x, y, pos.x, pos.y) < threshold) {
      y += offset;
    }
  }

  return { x, y };
}
