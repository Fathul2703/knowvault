/**
 * A small force-directed layout (Fruchterman–Reingold) for the knowledge graph. The graph holds
 * at most a couple of hundred entities, so a plain O(n²) simulation is fast enough and saves a
 * dependency. It is deterministic: the same graph is always drawn the same way, so the picture
 * does not jump around between visits.
 */

export type LayoutNode = { id: string; mentions: number };
export type LayoutEdge = { source: string; target: string; weight: number };
export type Point = { x: number; y: number };

export type LayoutOptions = {
  width: number;
  height: number;
  /** Distance kept free along the borders, for node circles and labels. */
  padding?: number;
  iterations?: number;
};

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
/** Measured on real graphs: lower lets unrelated entities pile up along the borders. */
const GRAVITY = 0.5;
/** Free space between two circles, about one line of label text. */
const LABEL_ROOM = 18;

/**
 * Positions for every node, inside the padded box. Nodes should come in order of importance:
 * the first ones start in the middle, which is where the layout keeps the best-connected ones.
 */
export function layoutGraph(
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  { width, height, padding = 40, iterations = 300 }: LayoutOptions,
): Map<string, Point> {
  const positions = new Map<string, Point>();
  const count = nodes.length;
  const cx = width / 2;
  const cy = height / 2;
  if (count === 0) {
    return positions;
  }
  if (count === 1) {
    positions.set(nodes[0].id, { x: cx, y: cy });
    return positions;
  }

  const innerWidth = Math.max(1, width - 2 * padding);
  const innerHeight = Math.max(1, height - 2 * padding);
  const k = 0.6 * Math.sqrt((innerWidth * innerHeight) / count);

  // Start on a sunflower spiral: spread out, no two nodes on the same spot, no randomness.
  const xs = new Float64Array(count);
  const ys = new Float64Array(count);
  const spread = Math.min(innerWidth, innerHeight) / 2;
  // Gravity strong enough that the mutual repulsion of all nodes balances it inside the box;
  // without it, entities that share no passage would be pushed against the borders.
  const gravity = (GRAVITY * count * k * k) / (spread * spread * spread);
  nodes.forEach((_, i) => {
    const r = spread * Math.sqrt((i + 0.5) / count);
    xs[i] = cx + r * Math.cos(i * GOLDEN_ANGLE);
    ys[i] = cy + r * Math.sin(i * GOLDEN_ANGLE);
  });

  const maxMentions = Math.max(1, ...nodes.map((node) => node.mentions));
  const radii = nodes.map((node) => nodeRadius(node.mentions, maxMentions));

  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const springs: Array<[number, number, number]> = [];
  for (const edge of edges) {
    const a = index.get(edge.source);
    const b = index.get(edge.target);
    if (a !== undefined && b !== undefined && a !== b) {
      // Strongly related entities pull harder, but a pair seen in many passages should not
      // collapse onto one point.
      springs.push([a, b, 1 + Math.log(Math.max(1, edge.weight))]);
    }
  }

  const dx = new Float64Array(count);
  const dy = new Float64Array(count);
  let temperature = Math.min(innerWidth, innerHeight) / 8;
  const cooling = temperature / (iterations + 1);

  for (let step = 0; step < iterations; step++) {
    dx.fill(0);
    dy.fill(0);

    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        let ddx = xs[i] - xs[j];
        let ddy = ys[i] - ys[j];
        let distance = Math.hypot(ddx, ddy);
        if (distance < 0.01) {
          // Nudge coinciding nodes apart in a fixed direction.
          ddx = 0.01 * (1 + ((i + j) % 3));
          ddy = 0.01;
          distance = Math.hypot(ddx, ddy);
        }
        const force = (k * k) / distance;
        const fx = (ddx / distance) * force;
        const fy = (ddy / distance) * force;
        dx[i] += fx;
        dy[i] += fy;
        dx[j] -= fx;
        dy[j] -= fy;
      }
    }

    for (const [a, b, strength] of springs) {
      const ddx = xs[a] - xs[b];
      const ddy = ys[a] - ys[b];
      const distance = Math.max(0.01, Math.hypot(ddx, ddy));
      const force = ((distance * distance) / k) * strength;
      const fx = (ddx / distance) * force;
      const fy = (ddy / distance) * force;
      dx[a] -= fx;
      dy[a] -= fy;
      dx[b] += fx;
      dy[b] += fy;
    }

    for (let i = 0; i < count; i++) {
      // Gravity keeps unconnected entities from drifting to the borders.
      // The box is usually wider than tall: pull harder vertically so the layout fills it.
      dx[i] += (cx - xs[i]) * gravity * spread;
      dy[i] += (cy - ys[i]) * gravity * spread * (innerWidth / innerHeight);
      const length = Math.hypot(dx[i], dy[i]);
      if (length > 0) {
        const move = Math.min(length, temperature);
        xs[i] += (dx[i] / length) * move;
        ys[i] += (dy[i] / length) * move;
      }
    }
    separate(xs, ys, radii);
    for (let i = 0; i < count; i++) {
      xs[i] = clamp(xs[i], padding, width - padding);
      ys[i] = clamp(ys[i], padding, height - padding);
    }
    temperature = Math.max(0.5, temperature - cooling);
  }

  nodes.forEach((node, i) => positions.set(node.id, { x: xs[i], y: ys[i] }));
  return positions;
}

/**
 * Pushes overlapping circles apart, keeping room for the label under each one. Forces alone
 * pull tightly related entities onto each other.
 */
function separate(xs: Float64Array, ys: Float64Array, radii: readonly number[]): void {
  for (let i = 0; i < radii.length; i++) {
    for (let j = i + 1; j < radii.length; j++) {
      const ddx = xs[j] - xs[i];
      const ddy = ys[j] - ys[i];
      const distance = Math.hypot(ddx, ddy);
      const needed = radii[i] + radii[j] + LABEL_ROOM;
      if (distance >= needed) {
        continue;
      }
      const push = (needed - distance) / 2;
      // Coinciding nodes separate in a fixed direction, so the result stays deterministic.
      const ux = distance > 0.01 ? ddx / distance : 1;
      const uy = distance > 0.01 ? ddy / distance : 0;
      xs[i] -= ux * push;
      ys[i] -= uy * push;
      xs[j] += ux * push;
      ys[j] += uy * push;
    }
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Circle radius for a node: the area grows with the number of mentions. */
export function nodeRadius(mentions: number, maxMentions: number): number {
  const share = maxMentions > 0 ? Math.max(0, mentions) / maxMentions : 0;
  return 5 + 13 * Math.sqrt(share);
}
