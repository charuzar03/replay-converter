# Apps Script Backend

This folder contains the Google Apps Script web app for one-battle sheet submissions.

## Deployment

1. Create an Apps Script project and add `Code.js` plus `appsscript.json`.
2. In **Project Settings > Script Properties**, set:
   - `BASIC_SPREADSHEET_ID`: the spreadsheet containing `Battle Data Raw`
   - `ADVANCED_SPREADSHEET_ID`: the spreadsheet containing `S4 Stats`
   - `BASIC_SHEET_NAME`: optional, defaults to `Battle Data Raw`
   - `ADVANCED_SHEET_NAME`: optional, defaults to `S4 Stats`
3. Deploy as a web app:
   - **Execute as**: Me
   - **Who has access**: Anyone
4. Configure the static site to post a hidden form field named `payload` to the web app URL.

## Request Shape

The web app expects one form field named `payload` containing JSON from `ReplayAutomation.buildSingleBattleAutomationPayload`, plus a `replaceExisting` boolean when the user has explicitly confirmed replacement.

Duplicates are detected by replay URL in `Battle Data Raw` column E and by `battle_id` in `S4 Stats` column A. A duplicate without `replaceExisting` returns `status: "duplicate"` and writes nothing.
