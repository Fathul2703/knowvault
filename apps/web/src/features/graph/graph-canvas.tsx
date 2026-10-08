"use client";

import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";

import { cx } from "@/components/ui";
import type { GraphEdge, GraphNode } from "@/lib/api/client";

import { entityPath, entityType, plural } from "./entity-types";
import { layoutGraph, nodeRadius } from "./layout";

/** Width used until the real one is measured (and in tests, which have no layout). */
const DEFAULT_WIDTH = 800;
/** Names written under the nodes when nothing is highlighted, fewer on narrow screens; the
 * others show on hover. */
const LABELLED_NODES = 14;
const PIXELS_PER_LABEL = 50;
const MAX_LABEL = 24;

export type GraphCanvasProps = {
  nodes: readonly GraphNode[];
  edges: readonly GraphEdge[];
  /** The entity under the pointer or keyboard focus, here or in the list. */
  active: string | null;
  onActiveChange: (id: string | null) => void;
  onOpen: (id: string) => void;
};

/** Entities sharing a passage with `id`, including `id` itself. */
export function neighbourhood(
  id: string | null,
  edges: readonly GraphEdge[],
): Set<string> {
  const ids = new Set<string>();
  if (id === null) {
    return ids;
  }
  ids.add(id);
  for (const edge of edges) {
    if (edge.source === id) {
      ids.add(edge.target);
    } else if (edge.target === id) {
      ids.add(edge.source);
    }
  }
  return ids;
}

function shortLabel(name: string): string {
  return name.length > MAX_LABEL ? `${name.slice(0, MAX_LABEL - 1)}…` : name;
}

/**
 * The graph as an SVG picture. Every node is a real link to the entity, so it works with the
 * keyboard and screen readers; the list next to it offers the same entities as text.
 */
export function GraphCanvas({
  nodes,
  edges,
  active,
  onActiveChange,
  onOpen,
}: GraphCanvasProps) {
  // Lay out in the real size of the box, one unit per pixel, so labels stay readable on
  // narrow screens instead of shrinking with a scaled picture.
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      const measured = Math.round(entry.contentRect.width);
      if (measured > 0) {
        setWidth(measured);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const height = graphHeight(width);
  const positions = useMemo(
    () => layoutGraph(nodes, edges, { width, height }),
    [nodes, edges, width, height],
  );
  const maxMentions = Math.max(1, ...nodes.map((node) => node.mentions));
  const highlighted = neighbourhood(active, edges);
  const labelCount = Math.min(
    LABELLED_NODES,
    Math.floor(width / PIXELS_PER_LABEL),
  );
  const labelled = new Set(nodes.slice(0, labelCount).map((node) => node.id));

  function open(event: MouseEvent<Element>, id: string) {
    // Keep new-tab clicks working; a plain click navigates without reloading the app.
    if (
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    ) {
      return;
    }
    event.preventDefault();
    onOpen(id);
  }

  return (
    <div ref={box}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        // Fills the box; the view box matches the measured width, so one unit is one pixel.
        className="block h-auto w-full select-none"
        role="group"
        aria-label="Entity graph"
        onMouseLeave={() => onActiveChange(null)}
      >
        <g aria-hidden="true">
          {edges.map((edge) => {
            const a = positions.get(edge.source);
            const b = positions.get(edge.target);
            if (!a || !b) {
              return null;
            }
            const lit =
              active !== null &&
              (edge.source === active || edge.target === active);
            return (
              <line
                key={`${edge.source}-${edge.target}-${edge.type}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                strokeWidth={Math.min(
                  6,
                  1 + Math.log2(Math.max(1, edge.weight)),
                )}
                className={cx(
                  "transition-opacity",
                  lit ? "stroke-slate-500" : "stroke-slate-300",
                  active !== null && !lit && "opacity-20",
                )}
              />
            );
          })}
        </g>
        {nodes.map((node) => {
          const point = positions.get(node.id);
          if (!point) {
            return null;
          }
          const radius = nodeRadius(node.mentions, maxMentions);
          const dimmed = active !== null && !highlighted.has(node.id);
          const showLabel =
            active === null ? labelled.has(node.id) : highlighted.has(node.id);
          const style = entityType(node.type);
          const description = `${node.name}, ${style.label.toLowerCase()}, ${plural(
            node.mentions,
            "mention",
            "mentions",
          )} in ${plural(node.documents, "document", "documents")}`;
          return (
            <a
              key={node.id}
              href={entityPath(node.id)}
              aria-label={description}
              className={cx(
                "group outline-none transition-opacity",
                dimmed && "opacity-25",
              )}
              onClick={(event) => open(event, node.id)}
              onMouseEnter={() => onActiveChange(node.id)}
              onFocus={() => onActiveChange(node.id)}
              onBlur={() => onActiveChange(null)}
            >
              <title>{description}</title>
              <circle
                cx={point.x}
                cy={point.y}
                r={radius}
                className={cx(
                  style.fill,
                  node.id === active
                    ? "stroke-slate-900"
                    : "stroke-white group-focus-visible:stroke-slate-900",
                )}
                strokeWidth={2}
              />
              {showLabel ? (
                <text
                  x={point.x}
                  y={point.y + radius + 12}
                  textAnchor="middle"
                  className={cx(
                    "fill-slate-700 stroke-white text-[11px] [paint-order:stroke]",
                    node.id === active && "fill-slate-950 font-semibold",
                  )}
                  strokeWidth={3}
                  strokeLinejoin="round"
                >
                  {shortLabel(node.name)}
                </text>
              ) : null}
            </a>
          );
        })}
      </svg>
    </div>
  );
}

/** Wide boxes get a landscape picture; narrow ones (phones) a squarer one. */
export function graphHeight(width: number): number {
  return Math.round(Math.min(560, Math.max(320, width * 0.62)));
}
