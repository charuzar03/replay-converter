## Problem Statement

League admins currently use two disconnected manual workflows after receiving a Wiglett replay analysis:

1. Paste the Wiglett output into the replay converter to generate a single `Battle Data Raw` line for the `S4 LBPP` spreadsheet.
2. Separately use the advanced stats tool to parse the replay URL into per-Pokemon advanced stats, then manually paste those rows into the `S4 Stats` tab of the `Pokemon Stats+ Helper` spreadsheet.

This split workflow is slow, repetitive, and easy to desynchronize. A single battle can end up present in one spreadsheet but missing or outdated in the other. The main user-facing workflow should stay centered on the existing Wiglett submission model, but one battle submission should update both spreadsheets together.

## Solution

Keep the current Wiglett-based submission model in the main replay converter, but turn it into a one-battle automation flow.

The user pastes one full Wiglett replay analysis into the main converter, chooses the winner and loser, reviews the generated output, and submits that single battle. The application then:

1. Generates the existing `Battle Data Raw` row from the Wiglett text.
2. Extracts the replay URL from the same Wiglett submission.
3. Parses that replay into advanced per-Pokemon stats for `S4 Stats`.
4. Sends both datasets together to an Apps Script web app.
5. Writes both spreadsheet targets atomically so the battle is either updated everywhere or nowhere.

The separate `Advanced Stat Updates (for Charu)` page remains available as a manual batch parsing tool for advanced stats generation. It is not part of the automated sheet-writing flow.

## User Stories

1. As a league admin, I want to paste one Wiglett output into the main converter, so that I can update all battle tracking for that match in one submission.
2. As a league admin, I want the main converter to keep the current Wiglett-based input model, so that I do not need to retrain users on a totally new workflow.
3. As a league admin, I want to choose the winner and loser before submission, so that the generated battle row stays aligned with the league's current manual conventions.
4. As a league admin, I want the converter to keep roster-based species correction, so that replay nicknames and form variants still resolve to the expected roster entries.
5. As a league admin, I want one submission to update both `Battle Data Raw` and `S4 Stats`, so that I do not have to perform a second paste flow for the same battle.
6. As a league admin, I want the advanced stats rows to be generated from the replay URL inside the Wiglett output, so that the advanced data comes from the same source battle as the basic row.
7. As a league admin, I want a single-battle submission model, so that the main public workflow stays simple and easy to recover when something goes wrong.
8. As a league admin, I want the application to reject empty or malformed Wiglett submissions, so that obviously bad input never reaches either spreadsheet.
9. As a league admin, I want the application to detect when the replay URL is missing from the Wiglett output, so that I understand why advanced stats cannot be generated.
10. As a league admin, I want the application to stop the submission if advanced replay parsing fails, so that the two spreadsheets cannot drift apart.
11. As a league admin, I want advanced parser warnings to be visible without blocking submission, so that I can keep the workflow moving while still seeing possible edge-case issues.
12. As a league admin, I want duplicate battles to be detected before writing, so that accidental resubmissions do not silently create conflicting rows.
13. As a league admin, I want duplicate replacement to require an explicit second confirmation, so that existing data is not overwritten by a stray click.
14. As a league admin, I want replacement to rewrite both the `Battle Data Raw` entry and every matching `S4 Stats` row for that battle, so that corrected replays stay consistent across spreadsheets.
15. As a league admin, I want the automated upload path to work from the existing static site, so that the current hosting model can remain in place.
16. As a league admin, I want the upload transport to be reliable from GitHub Pages to Apps Script, so that browser cross-origin rules do not break the tool.
17. As a league admin, I want public users to be able to submit without authenticating to Google, so that league ops are not blocked on per-user sheet access.
18. As a league admin, I want lightweight server-side validation around public submissions, so that the endpoint does not accept arbitrary junk rows.
19. As a league admin, I want short-lived server-side preview state instead of a permanent audit tab, so that the spreadsheets stay lean and fast on desktop and mobile.
20. As Charu, I want the advanced stats page to remain available for manual batch outputs, so that I can continue using it for larger backfills or one-off checks.
21. As Charu, I want the advanced page to remain separate from the public uploader, so that the public flow stays simple while the admin tool stays powerful.
22. As a future maintainer, I want the Apps Script code versioned alongside the converter, so that the browser flow and sheet-writing logic can evolve together.
23. As a future maintainer, I want deployment instructions for the Apps Script web app, so that the endpoint can be re-deployed without rediscovering the required Google settings.
24. As a future maintainer, I want the automated flow to retain a manual fallback posture, so that a temporary endpoint failure does not destroy the existing operational path.
25. As a future maintainer, I want the advanced stats generation seam to stay as high-level as possible, so that tests can target externally visible behavior instead of internal parser details.

## Implementation Decisions

- The existing main replay converter remains the primary user-facing entry point and keeps the current Wiglett submission model. The feature extends the current convert-and-copy workflow into a convert-preview-submit workflow rather than replacing it with a URL-only flow.
- The automated main flow is intentionally single-battle only. Each submission starts from one Wiglett output and may write one `Battle Data Raw` row plus the corresponding advanced stats rows for one replay.
- The main upload flow still depends on the winner and loser selectors already present in the converter UI. Those selections remain part of the contract for building the `Battle Data Raw` payload.
- The replay URL extracted from the Wiglett output is the source of truth for advanced stats generation in the main flow.
- The advanced stats parser used by the browser-facing advanced page is also the seam reused by the main uploader for `S4 Stats` generation. The desired seam is one high-level parse operation that accepts replay content plus replay metadata and returns advanced rows plus warnings.
- The browser remains responsible for generating the client-side payloads. It prepares:
  - the `Battle Data Raw` line from the Wiglett submission
  - the advanced stats rows for the replay URL
  - the duplicate/replace intent for the current submission
- An Apps Script web app is the only sheet-writing backend. It runs as the deploying user and accepts public submissions from the static site.
- The browser-to-Apps Script integration uses a hidden form and iframe bridge instead of `fetch()`. This is the chosen transport to avoid GitHub Pages to Apps Script CORS issues while still allowing the page to receive structured responses.
- The Apps Script layer validates incoming requests, checks duplicates, and writes both spreadsheet targets as one logical operation. From the user's perspective, the write is atomic: if advanced stats generation or validation fails, neither spreadsheet should be updated.
- Duplicate handling rules are:
  - `Battle Data Raw` duplicates are keyed by replay URL.
  - `S4 Stats` duplicates are keyed by `battle_id`.
  - first submission attempt on an existing battle returns a duplicate result
  - replacement requires a second explicit user action
  - replacement rewrites both the existing `Battle Data Raw` row and all matching `S4 Stats` rows
- Advanced parser warnings are not fatal. A successful parse with warnings can still be submitted, but warnings must be visible in the UI before the user confirms submission.
- Public submission is allowed, but the endpoint should still reject malformed or incomplete requests. Lightweight protections are preferred over user authentication.
- Server-side temporary state should stay lightweight. The chosen direction is short-lived preview or request state in Apps Script properties and/or cache rather than permanent audit data stored in either spreadsheet.
- No new spreadsheet logging tab should be introduced. The spreadsheets themselves remain the durable record of successful submissions.
- The separate advanced stats page remains a distinct admin workflow. It continues supporting manual batch replay parsing and manual TSV/CSV output, and it does not auto-submit to Google Sheets.
- The browser and Apps Script code should be versioned together in the repo. The Apps Script source should live in a dedicated folder so deployment artifacts and instructions are kept close to the web UI that depends on them.
- The implementation should preserve the existing manual mental model of the main page. Users should still recognize the converter as a Wiglett-to-battle-data tool, with automation added on top rather than a brand new product.

## Testing Decisions

- Good tests should verify externally visible behavior and user outcomes rather than internal implementation details. In practice, that means testing payload generation, parse outcomes, duplicate decisions, and atomic submission behavior instead of asserting on private helper structure.
- The highest-value seam to test is the high-level replay parsing and payload-building flow, because it already reflects how the application works from the user's point of view.
- Existing parser regression tests provide prior art for behavior-focused testing around replay parsing. Similar tests should continue to use minimal replay snippets and assert on output rows and warnings rather than on parser internals.
- The Wiglett conversion logic should be tested at the UI-logic seam that turns one pasted Wiglett output plus winner/loser selections into:
  - one `Battle Data Raw` line
  - one extracted replay URL
  - one advanced stats parse request
- The advanced stats integration in the main flow should be tested with successful parse, successful parse with warnings, and failed parse cases.
- The duplicate and replacement contract should be tested at the request/response seam between the browser and Apps Script:
  - new battle submission
  - duplicate detection
  - explicit replacement
  - rejection of malformed submissions
- The all-or-nothing behavior should be tested as observable submission outcomes rather than spreadsheet mutation details. A failure on the advanced side should surface as a failed submission with no successful completion response.
- The manual advanced page should retain regression coverage around batch parsing and export formatting so the new main-flow automation work does not accidentally degrade the Charu-only tool.

## Out of Scope

- Replacing Wiglett with a URL-only public workflow.
- Multi-battle or batch submission in the main replay converter.
- Automatic sheet-writing from the `Advanced Stat Updates (for Charu)` page.
- A permanent audit log tab or analytics dashboard inside either spreadsheet.
- Requiring Google authentication for end users.
- A broader replay management product beyond the existing battle conversion and advanced stats workflows.
- Reworking league spreadsheet formulas, derived tabs, or ranking logic outside the raw ingestion targets.
- General-purpose admin tools for backfills, season migration, or mass duplicate cleanup beyond the existing manual advanced workflow.

## Further Notes

- The current repo already exposes the two important user-facing surfaces: the Wiglett-based main converter and the separate advanced stats page. This feature should deepen the connection between them without collapsing them into one overloaded interface.
- The existing main converter already reads live roster data from the league spreadsheet. That behavior should continue to anchor species correction and coach-facing output consistency.
- The advanced parser currently operates in-browser and is already framed as a manual stats-generation tool. Reusing that logic for single-battle automation in the main flow keeps the implementation close to the system the project already has.
- The deployment story matters because the final operational workflow depends on an Apps Script web app. The implementation should include clear instructions for deployment settings, especially public access and execute-as-owner behavior.
