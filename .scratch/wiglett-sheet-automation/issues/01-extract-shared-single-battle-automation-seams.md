# 01 — Extract shared single-battle automation seams

**What to build:** make the existing replay converter capable of turning one Wiglett submission into a complete client-side automation payload: one basic battle row, one replay URL, and one advanced stats result with warnings, without changing the current user-facing workflow yet.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A single high-level client-side flow can consume one Wiglett submission plus winner/loser selections and produce the full submission-ready payload.
- [ ] Advanced stats generation for one replay is exposed through a high-level seam that returns rows plus warnings and can be reused by both the main flow and the existing advanced tool.

