# LeanAtlas v0.2.0

Topic-label styling for the explorer.

- New **topics panel**: show/hide labels, base size, color, opacity, and a
  zoom-follow toggle, with reset. Styling is session-local (never enters the
  URL deep link), and defaults reproduce the previous look exactly.
- **Zoom-following labels** (default on): topic-band labels now scale with
  the camera — larger as you zoom into a band, smaller on the way out,
  clamped to 0.5×–4× so they stay readable at overview and on screen when
  deep-zoomed.
- Panel layout: the edge and topics panels share a left column that lets
  pointer events pass through everywhere except the panels themselves.

Full changelog: https://github.com/VANvonZHANG/LeanAtlas/compare/v0.1.0...v0.2.0
