# 05 — Preserve advanced manual batch workflow during automation rollout

**What to build:** keep the Charu-only advanced stats page working as a separate manual batch parser and export tool while the new main-flow automation reuses the same high-level advanced parsing seam safely.

**Blocked by:** 01 — Extract shared single-battle automation seams.

**Status:** ready-for-agent

- [ ] The advanced stats page still supports manual batch parsing and export without automatic Google Sheets writes.
- [ ] Reusing advanced parsing logic for the main automation flow does not regress the current advanced manual workflow.

