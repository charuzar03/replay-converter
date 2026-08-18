# 03 — Wire main converter preview into submit-ready automation

**What to build:** turn the main Wiglett-based converter into a one-battle preview-and-submit flow that shows the generated battle row, advanced warnings, and end-to-end submission status through the Apps Script bridge.

**Blocked by:** 01 — Extract shared single-battle automation seams, 02 — Add Apps Script backend for atomic two-sheet writes.

**Status:** ready-for-agent

- [ ] A user can paste one Wiglett output, review the generated data, and submit that battle from the main converter.
- [ ] The main flow can communicate with Apps Script through the iframe bridge and show success, validation errors, parse failures, and non-fatal warnings.

