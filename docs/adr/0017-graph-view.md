# ADR 0017: Graph view — an SVG drawn with our own force layout

- Status: Accepted
- Date: 2026-10-08

## Context

The knowledge graph (ADR 0015, 0016) was only reachable through the API. The architecture plans a
read-only view of it (§5, Phase 5). The overview endpoint returns at most 200 entities, and the
web app asks for the 60 most mentioned. The view must:

- work with the production Content Security Policy, which allows styles only from the
  stylesheet and from nonce-tagged elements, so no inline `style` attributes;
- be usable with the keyboard and a screen reader, not only with a mouse;
- stay readable on a phone;
- not add a dependency that the dependency audit then has to keep clean.

Graph libraries (d3-force, Cytoscape, Sigma, react-force-graph) solve far bigger problems:
thousands of nodes, WebGL, dragging and physics running live. They also draw on a canvas, which
is invisible to assistive technology, or set inline styles.

## Decision

1. **Our own force layout** (`features/graph/layout.ts`): Fruchterman–Reingold with gravity and a
   collision pass. It is a pure function, about 150 lines.
   - **Deterministic.** Nodes start on a sunflower spiral, with no randomness, so the same graph
     is always drawn the same way.
   - **Gravity scales with the number of entities.** Entities that share no passage stay inside
     the box instead of piling up along its borders.
   - **Collision pass.** It keeps a label's height between circles.
   - **Measured on the evaluation corpus** (27 entities):
     - Before the gravity fix, 23 of 27 nodes were pressed against the border.
     - After it, none were.
     - With 60 entities the layout takes about 40 ms.
2. **SVG, one unit per pixel.** The canvas measures its width with a `ResizeObserver` and lays
   the graph out in that size. Labels therefore keep their font size on a phone instead of
   shrinking with a scaled picture. Fewer names are written when the canvas is narrow.
3. **Accessible by construction.**
   - Every node is an SVG `<a>` with a descriptive label, for example "ERR_4711, code,
     4 mentions in 1 document".
   - The list next to the picture offers the same entities as ordinary links.
   - Hovering or focusing an entity in either place highlights its neighbours.
   - Colours and sizes come from Tailwind classes and SVG attributes, never from inline styles.
4. **Pages.**
   - `/graph` shows the overview, scoped by `?collection=` or `?document=`. A document page
     links to its own graph.
   - `/graph/entities/{id}` shows the entity: the passages that mention it, grouped by document
     and linked to `#chunk-n`, its aliases with their similarity, its related entities, and a
     full-text search for its name.

## Consequences

- **Gained:**
  - No new dependency and no change to the CSP.
  - The view works without a mouse.
  - The E2E test now covers the graph: it finds an entity of the new note, opens it, sees the
    code mentioned with it and follows the passage link back into the note.
- **Given up:**
  - No dragging, zooming or panning.
  - The layout runs once per graph and screen width, not live.
  - Beyond about 150 entities on a phone the picture gets crowded. The page asks for 60, and
    the list stays usable at any size.
- **Revisit** if the overview should show far more entities, or if users need to rearrange the
  picture. A library with a canvas renderer would then be worth its cost, with the list kept as
  the accessible alternative.
