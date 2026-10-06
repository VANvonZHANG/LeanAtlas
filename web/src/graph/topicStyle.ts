/** Topic-band label style, adjustable at runtime via the topic panel. Like
 * the edge style, this is session-local: label styling never enters the URL
 * (deep links stay semantic) nor localStorage. */
export interface TopicStyle {
  visible: boolean;
  /** Base font size in px at camera ratio 1 (the fitted overview). */
  size: number;
  color: string;
  opacity: number;
  /** World-anchor the labels: scale with 1/ratio (clamped by topicScale),
   * so labels track the topic bands they name as the camera moves. */
  followZoom: boolean;
}

/** Defaults equal the pre-P1.6 hardcoded CSS look (styles.css .topic-label:
 * font-size 20px / color #cfd8ff / opacity .8) — untouched panel = zero
 * visual regression at ratio 1. */
export const TOPIC_STYLE_DEFAULTS: TopicStyle = {
  visible: true,
  size: 20,
  color: "#cfd8ff",
  opacity: 0.8,
  followZoom: true,
};

export function cloneTopicStyleDefaults(): TopicStyle {
  return { ...TOPIC_STYLE_DEFAULTS };
}
