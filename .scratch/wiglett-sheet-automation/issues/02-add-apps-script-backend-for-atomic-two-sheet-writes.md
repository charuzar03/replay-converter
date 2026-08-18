# 02 — Add Apps Script backend for atomic two-sheet writes

**What to build:** create a deployable Apps Script web app that accepts one battle submission, validates it, checks for duplicates, and writes both spreadsheet targets together so a battle is either updated everywhere or nowhere.

**Blocked by:** 01 — Extract shared single-battle automation seams.

**Status:** ready-for-agent

- [ ] The backend can accept one submission containing the basic battle row, the advanced stats rows, and duplicate/replace intent.
- [ ] The backend can validate, detect duplicates by replay URL and battle id, and write `Battle Data Raw` plus `S4 Stats` as one logical operation.

