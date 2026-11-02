// The four answer shapes. Each choice is told apart by its shape, its letter and its words, so no
// one needs to tell colours apart to play. The shapes are drawn here, not taken from any game.
export const SHAPES = ["circle", "triangle", "square", "diamond"] as const;
export type ShapeName = (typeof SHAPES)[number];

export function Shape({ index, className }: { index: number; className?: string }) {
  const shape = SHAPES[index % SHAPES.length];
  return (
    <svg className={`shape shape-${shape}${className ? " " + className : ""}`} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      {shape === "circle" && <circle cx="20" cy="20" r="15" />}
      {shape === "triangle" && <polygon points="20,4 37,35 3,35" />}
      {shape === "square" && <rect x="6" y="6" width="28" height="28" />}
      {shape === "diamond" && <polygon points="20,2 38,20 20,38 2,20" />}
    </svg>
  );
}
