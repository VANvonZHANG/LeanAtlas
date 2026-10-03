import { useEffect, useState } from "react";
import { useSigma } from "@react-sigma/core";
import type { TopicRow } from "../graph/loadData";

interface Anchor { id: string; label: string; x: number; y: number }

export default function TopicOverlay({ topics }: { topics: TopicRow[] }) {
  const sigma = useSigma();
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const [projections, setProjections] = useState<{ id: string; left: number; top: number; visible: boolean }[]>([]);

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
    const project = () => {
      const w = sigma.getContainer().clientWidth, h = sigma.getContainer().clientHeight;
      setProjections(
        anchors.map((a) => {
          const p = sigma.graphToViewport({ x: a.x, y: a.y });
          const visible = p.x > -80 && p.x < w + 80 && p.y > -24 && p.y < h + 24;
          return { id: a.id, left: p.x, top: p.y, visible };
        }),
      );
    };
    project();
    sigma.on("afterRender", project);
    return () => { sigma.removeListener("afterRender", project); };
  }, [sigma, anchors]);

  return (
    <div className="topic-overlay">
      {projections.map((p) => {
        const a = anchors.find((x) => x.id === p.id)!;
        return (
          <div
            key={p.id}
            className="topic-label"
            style={{ left: p.left, top: p.top, display: p.visible ? "" : "none" }}
          >
            {a.label}
          </div>
        );
      })}
    </div>
  );
}
