import { describe, expect, it } from "vitest";

import { layoutGraph, nodeRadius } from "@/features/graph/layout";

const box = { width: 800, height: 520, padding: 40 };

function nodes(count: number) {
  return Array.from({ length: count }, (_, i) => ({ id: `n${i}`, mentions: count - i }));
}

describe("layoutGraph", () => {
  it("handles empty and single-node graphs", () => {
    expect(layoutGraph([], [], box).size).toBe(0);
    expect(layoutGraph(nodes(1), [], box).get("n0")).toEqual({ x: 400, y: 260 });
  });

  it("keeps every node inside the padded box", () => {
    const many = nodes(60);
    const edges = many.slice(1).map((node, i) => ({ source: "n0", target: node.id, weight: i + 1 }));
    for (const point of layoutGraph(many, edges, box).values()) {
      expect(point.x).toBeGreaterThanOrEqual(40);
      expect(point.x).toBeLessThanOrEqual(760);
      expect(point.y).toBeGreaterThanOrEqual(40);
      expect(point.y).toBeLessThanOrEqual(480);
    }
  });

  it("draws the same graph the same way every time", () => {
    const graph = nodes(12);
    const edges = [
      { source: "n0", target: "n1", weight: 3 },
      { source: "n2", target: "n3", weight: 1 },
    ];
    expect([...layoutGraph(graph, edges, box)]).toEqual([...layoutGraph(graph, edges, box)]);
  });

  it("puts related entities closer together than unrelated ones", () => {
    const graph = nodes(10);
    const positions = layoutGraph(graph, [{ source: "n4", target: "n7", weight: 5 }], box);
    const distance = (a: string, b: string) => {
      const p = positions.get(a)!;
      const q = positions.get(b)!;
      return Math.hypot(p.x - q.x, p.y - q.y);
    };
    const others = graph
      .filter((node) => node.id !== "n4" && node.id !== "n7")
      .map((node) => distance("n4", node.id));
    expect(distance("n4", "n7")).toBeLessThan(Math.min(...others));
  });

  it("ignores edges to entities that are not drawn and self-loops", () => {
    const positions = layoutGraph(
      nodes(3),
      [
        { source: "n0", target: "missing", weight: 1 },
        { source: "n1", target: "n1", weight: 1 },
      ],
      box,
    );
    expect(positions.size).toBe(3);
    for (const point of positions.values()) {
      expect(Number.isFinite(point.x) && Number.isFinite(point.y)).toBe(true);
    }
  });
});

describe("nodeRadius", () => {
  it("grows with mentions, from a readable minimum", () => {
    expect(nodeRadius(0, 10)).toBe(5);
    expect(nodeRadius(10, 10)).toBe(18);
    expect(nodeRadius(3, 10)).toBeGreaterThan(nodeRadius(1, 10));
  });
});
