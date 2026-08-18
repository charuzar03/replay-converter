# 04 — Add duplicate and replace confirmation across both targets

**What to build:** add duplicate detection and explicit replace confirmation so an existing battle cannot be overwritten accidentally, and confirmed replacement updates both spreadsheet targets together.

**Blocked by:** 02 — Add Apps Script backend for atomic two-sheet writes, 03 — Wire main converter preview into submit-ready automation.

**Status:** ready-for-agent

- [ ] The first submission attempt on an existing battle returns a duplicate result instead of writing data.
- [ ] A second explicit replace action rewrites both the matching `Battle Data Raw` row and the matching `S4 Stats` rows for that battle.

