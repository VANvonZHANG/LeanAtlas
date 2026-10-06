import { cloneTopicStyleDefaults } from "../graph/topicStyle";
import { topicStyleStore } from "../state/stores";
import { useAtomValue } from "../hooks/useAtomValue";

/** Topic-label controls: show/hide, base size, color, opacity, and the
 * zoom-follow toggle. Session-local like all style state; reset restores the
 * in-code defaults (which equal the pre-P1.6 look at ratio 1). */
export default function TopicPanel() {
  const style = useAtomValue(topicStyleStore);
  const patch = (p: Partial<typeof style>) =>
    topicStyleStore.set({ ...topicStyleStore.get(), ...p });

  return (
    <div className="panel topic-panel">
      <label className="row">
        <input
          type="checkbox" aria-label="show topic labels" checked={style.visible}
          onChange={(e) => patch({ visible: e.target.checked })}
        />
        topics
      </label>
      <label className="row">
        size {style.size}px
        <input
          type="range" min={10} max={48} step={1} value={style.size}
          onChange={(e) => patch({ size: Number(e.target.value) })}
        />
      </label>
      <div className="row">
        <span className="style-label">color</span>
        <input
          type="color" value={style.color}
          onChange={(e) => patch({ color: e.target.value })}
        />
        <span className="style-label">opac</span>
        <input
          type="range" min={0.2} max={1} step={0.05} value={style.opacity}
          onChange={(e) => patch({ opacity: Number(e.target.value) })}
        />
      </div>
      <label className="row">
        <input
          type="checkbox" aria-label="scale labels with zoom" checked={style.followZoom}
          onChange={(e) => patch({ followZoom: e.target.checked })}
        />
        follow zoom
      </label>
      <button className="reset" onClick={() => topicStyleStore.set(cloneTopicStyleDefaults())}>
        reset
      </button>
    </div>
  );
}
