# Composio / Google Sheets requirements

`sheets_io.py` doesn't call Composio itself — the Claude agent running this skill
does, via whatever Composio Google Sheets / Google Drive MCP toolkit is connected
to the session. This doc lists the exact actions the skill needs and the order to
call them in. Names are Composio's standard `GOOGLESHEETS_*` / `GOOGLEDRIVE_*`
action families; use whatever the connected toolkit actually exposes under
those names.

## 1. Identify the correct connected account (mandatory, before any write)

1. List active Composio connections for Google Sheets / Google Drive
   (e.g. `COMPOSIO_LIST_CONNECTIONS` or the account-listing action of the
   connected toolkit).
2. For each Google-type connection, resolve the authenticated account email
   (e.g. via a `GOOGLEDRIVE_GET_ABOUT` / `whoami`-style call, or by reading the
   connection metadata Composio returns).
3. Compare against the known NODOTO AGENCY Google account. This repo's existing
   Gmail-sending pipeline (see `docs/outreach_playbook.md`) already sends from
   3 NODOTO Gmail accounts via Composio — cross-check against that same
   connection set/entity first, since it's the account already known to be
   correct for this project.
4. If exactly one Google Sheets-capable connection matches NODOTO -> use it.
   If zero or more than one plausible match exists and the correct one cannot
   be determined with certainty -> **STOP. Do not write anything.** Report the
   ambiguity in the run output (see `../scripts/report.py`) and fall back to
   `write_csv_mirror()` only.

## 2. Find or create the operative spreadsheet

1. Search Drive for spreadsheets already used for NODOTO lead operations
   (e.g. `GOOGLEDRIVE_SEARCH_FILES` filtered to `mimeType='application/vnd.google-apps.spreadsheet'`
   owned/shared with the verified account). Look for names containing
   "nodoto", "leads", "prospección", "prospects".
2. If one exists: use it. Do **not** create a second one ("Leads Final 2" is
   explicitly forbidden by the playbook).
3. If none exists: create exactly one spreadsheet (e.g. `NODOTO Leads —
   Operational Base`) with worksheets `Qualified Leads`,
   `Candidates - Owner Phone Missing`, and `Run Log`. Record its spreadsheet ID,
   name, and the verified account email in the run report and in
   `docs/methodology_and_status.md` per the existing repo convention.

## 3. Read before writing

1. Read the header row of the target worksheet (`GOOGLESHEETS_GET_SHEET_NAMES`,
   then a range read of row 1, e.g. `GOOGLESHEETS_BATCH_GET`).
2. Read existing data rows (at least the columns dedupe needs: Business Name,
   Owner Name, Owner Phone, Website, Instagram) and feed them through
   `dedupe.load_sheet_rows()`.
3. Note the current last row index — this is `rows_before` for `verify_write()`.

## 4. Reconcile schema

Call `sheets_io.map_to_existing_header(existing_header)`. If the sheet has no
header yet (brand new), write `schema.COLUMNS` as row 1 first.

## 5. Write (append-only)

Use an append action (e.g. `GOOGLESHEETS_APPEND_DIMENSION` /
`GOOGLESHEETS_BATCH_UPDATE` with an append range, or the toolkit's dedicated
"append row(s)" action). **Never** use a clear/overwrite/replace-worksheet
action. Only `Qualified Leads` rows that passed `scoring.run_qualification_gate`
go to the `Qualified Leads` worksheet; rows with status
`OWNER_PHONE_MISSING` go to `Candidates - Owner Phone Missing` instead.

## 6. Verify

Re-read the worksheet, compute `rows_after`, and call
`sheets_io.verify_write(...)`. If it returns `ok=False`, **stop** — do not
retry blindly, do not attempt to "fix" by writing again. Surface the exact
message in the run report.

## 7. CSV mirror — always

Regardless of whether steps 1-6 succeeded, call `sheets_io.write_csv_mirror()`
so a local, manually-importable CSV always exists under
`skills/nodoto-lead-hunter/output/`. If step 1 or step 5/6 failed, this CSV
mirror becomes the actual deliverable for that run — tell the user plainly
that Sheets could not be verified/written and here are the CSVs instead.
