import { useEffect, useRef, useState } from "react";
import { useSigma } from "@react-sigma/core";
import { projectAnchors, topicScale, type Anchor } from "../graph/projection";
import { topicFilterStore, topicStyleStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";
import type { TopicRow } from "../graph/loadData";

/**
 * Topic band labels as a DOM overlay. Anchors are computed once; positions
 * are written straight to the label elements on every afterRender —
 * translate3d only (no layout), no React state — so camera motion never
 * schedules a React commit. React owns only the user-facing bits: the
 * filtered class, the click handler, and the label style (inline); position +
 * zoom scale stay direct DOM writes.
 */
export default function TopicOverlay({ topics }: { topics: TopicRow[] }) {
  const sigma = useSigma();
  const filter = useAtomValue(topicFilterStore);
  const style = useAtomValue(topicStyleStore);
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const labelRefs = useRef(new Map<string, HTMLDivElement>());

  useEffect(() => {
    const g = sigma.getGraph();
    const acc = new Map<string, { sum: number; cnt: number }>();
    g.forEachNode((_n, attrs) => {
      const t = attrs.topic as string;
      const cur = acc.get(t) ?? { sum: 0, cnt: 0 };
      acc.set(t, { sum: cur.sum + (attrs.x as number), cnt: cur.cnt + 1 });
    });
    setAnchors(
      topics
        .filter((t) => acc.has(t.id))
        .map((t) => {
          const a = acc.get(t.id)!;
          return { id: t.id, label: t.label, x: a.sum / a.cnt, y: -t.y };
        }),
    );
  }, [sigma, topics]);

  useEffect(() => {
    if (anchors.length === 0) return;
    const writePositions = () => {
      const container = sigma.getContainer();
      // live snapshots, not closure captures: the effect must not re-run on
      // style flips (inline styles cover the React side; this covers the
      // per-frame transform scale).
      const st = topicStyleStore.get();
      const k = topicScale(sigma.getCamera().getState().ratio, {
        followZoom: st.followZoom,
      });
      const projected = projectAnchors(
        anchors,
        { width: container.clientWidth, height: container.clientHeight },
        (p) => sigma.graphToViewport(p),
      );
      for (const p of projected) {
        const el = labelRefs.current.get(p.id);
        if (!el) continue;
        // transform-only positioning: no layout; the -50% centering that used
        // to live in CSS is folded into the written matrix.
        el.style.transform =
          `translate3d(${p.x}px, ${p.y}px, 0) translate(-50%, -50%) scale(${k})`;
        el.style.display = p.visible ? "" : "none";
      }
    };
    // run once now (refs are attached before this effect body runs) instead
    // of waiting for sigma's first afterRender.
    writePositions();
    sigma.on("afterRender", writePositions);
    // a style flip at a still camera never triggers afterRender; re-run the
    // write once so the new scale takes effect immediately.
    const unsubStyle = topicStyleStore.subscribe(writePositions);
    return () => {
      sigma.removeListener("afterRender", writePositions);
      unsubStyle();
    };
    // NB: labelRefs is NOT cleared here — React StrictMode remounts effects
    // without re-running ref callbacks, so a cleanup-time clear would orphan
    // the labels (the map stays empty while the divs live on). Ref callbacks
    // own map membership via real DOM attach/detach.
  }, [sigma, anchors]);

  // The overlay container stays pointer-events:none, but each label opts back
  // in (styles.css). SigmaContainer renders children AFTER `.sigma-container`
  // inside `.react-sigma`, and sigma binds its MouseCaptor to its own mouse
  // canvas inside `.sigma-container` — a DOM sibling below the labels. A click
  // on a label is dispatched to the label and never reaches that canvas, so
  // sigma's clickStage (which clears the pin) cannot fire on label clicks and
  // no stopPropagation is needed.
  return (
    <div
      className="topic-overlay"
      style={{ display: style.visible ? undefined : "none" }}
    >
      {anchors.map((a) => (
        <div
          key={a.id}
          ref={(el) => {
            if (el) labelRefs.current.set(a.id, el);
            else labelRefs.current.delete(a.id);
          }}
          className={"topic-label" + (filter === a.id ? " filtered" : "")}
          style={{
            fontSize: `${style.size}px`,
            color: style.color,
            opacity: filter === a.id ? 1 : style.opacity,
          }}
          onClick={() => {
            const cur = topicFilterStore.get();
            topicFilterStore.set(cur === a.id ? null : a.id);
          }}
        >
          {a.label}
        </div>
      ))}
    </div>
  );
}
