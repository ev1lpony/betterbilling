# BetterBilling — Recovered Master

This is the consolidated recovery build created after comparing the available
legacy reconstruction, the BetterBilling Git history, the October 2025
speed-first GUI, and the March 2026 JSON/editing refactors.

## Compact interface

The app now uses a consistent, compact design with vertically stacked entry
fields beside the invoice table. Add sits directly below the fields; Tab,
Enter, Ctrl+D, and Ctrl+Enter keep their existing behavior. The invoice steps
remain Details → Services → Costs → Review & save. Flat fees retain their
existing shortcut to Costs.

Help is always available at the top of the app or through F1. It opens the
relevant offline guide with practical examples for dates, hours, rates, costs,
editing, saving, and backups. Close Help or press Escape to return to the same
field and draft. Review shows a formatted invoice and a total that stays visible
while scrolling. Save keeps the editable invoice; Save + Export PDF keeps both
the editable invoice and its PDF.

Settings → Appearance offers Light and Dark modes, plus Easy Reading for larger
text throughout the app and roomier invoice rows. Light and the original compact
text size are the defaults. Preferences apply immediately and are remembered
between launches. Back from Settings returns to the screen and entry field you
were using. Appearance preferences affect the screen; exported PDFs retain
their original design.

## What this version deliberately preserves

- Fast keyboard-first invoice entry
- Explicit service/cost tab order
- Enter-to-add workflow
- Ctrl+D to prefill/duplicate the last service or cost
- `Remove last service`
- Editable service and cost tables
- Default hourly rate
- Per-service hourly rates
- Exact duplicate service prevention
- Review-time dedupe for imported/old invoice data
- Flat-fee invoices
- Costs
- JSON-backed editable invoices
- Save / Save + Export / Save As New
- Portable `data/pdfs`, `data/json`, and `data/letterheads`
- Original Letter/Helvetica invoice design
- Original 15 mm left margin
- Original 2.5-inch letterhead reservation
- Original service widths `[25, 80, 25, 30, 30]`
- Original cost widths `[80, 30, 30, 30]`
- Repeating table headers
- Wrapped long service descriptions
- `TOTAL HOURS BILLED`
- Total service fees, total costs, and boxed grand total

## Bugs/regressions fixed while consolidating

1. **Sorted table / wrong-row edit bug**
   The latest code displayed services sorted by date but later edited
   `invoice.services[row]`, which can be the wrong underlying object if entry
   order differs from date order. Recovered Master gives every line a stable ID
   and edits by ID.

2. **Duplicate-edit mutation bug**
   The latest edit handler could mutate a service and only afterward discover
   that the edit created a duplicate. Recovered Master validates a tentative
   copy first and only commits it after validation succeeds.

3. **Lost explicit tab order**
   October 2025 intentionally set tab order for rapid entry; the March 2026
   refactor removed those calls. They are restored.

4. **Lost review-time dedupe**
   October automatically removed duplicate service lines before review. March
   removed this method while adding stricter entry validation. Recovered Master
   keeps both defenses.

5. **Save-As-New JSON/PDF suffix mismatch**
   JSON and PDF filenames were uniquified independently. If only one side had a
   collision, the two files could get different `(n)` suffixes. Recovered
   Master allocates the pair together.

6. **Total hours**
   The later repo displays hours in the status bar but did not emit
   `TOTAL HOURS BILLED` in the PDF. That recovered behavior is restored and can
   be disabled in Settings.

## What is still intentionally NOT implemented

These were not actually complete in the recovered repository and should not be
pretended to be recovered functionality:

- Real letterhead image/template management (`letterheads.py` was empty)
- Database-backed client/contact management (`db.py` was empty)
- Split model/PDF utility modules from the old repo stubs (this build now does
  implement those cleanly)
- Licensing / activation
- User accounts / cloud sync / SaaS hosting
- Email sending
- Payment processing / paid-unpaid tracking
- Installer / signed Windows executable
- Auto-update

Those are phase-two product features, not missing pieces of the old billing
workflow.

## Run

On this Windows workspace, double-click `RUN_BETTERBILLING.bat`. The project
virtual environment is ready. Normal invoice creation and saving work offline;
the first dependency installation requires Internet access.

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Development tests

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary invoice folders and settings. They cover models, legacy
JSON, malformed data, settings recovery, save failures, collisions, real PDF
pagination, and Qt keyboard/editing behavior. The original direct command
`python tests\test_core.py` also works after installing development dependencies.

## First stabilization cycle

- New invoices and Save As New preserve existing files, including collisions
  with only one half of a JSON/PDF pair.
- JSON writes are atomic. Save + Export stages both outputs and restores prior
  files after ordinary replacement failures; failed PDF rendering leaves saved
  records intact. A power loss between two final replacements remains a limit
  of separate JSON/PDF files.
- Invalid imported dates, rows, numbers, and unsupported schemas fail visibly;
  valid legacy records remain editable, with repaired missing/repeated IDs.
- Imported numeric precision and large values survive unrelated edits.
- New Invoice and closing protect unsaved metadata, lines, and unfinished entry
  drafts. A Save saves added rows; unfinished forms remain marked unsaved.
- Service dates stay in place after adding a line. Enter adds; Ctrl+D prefills;
  Ctrl+Enter advances from Services to Costs and from Costs to Review.
- PDF descriptions wrap and paginate across services, costs, and flat fees.
  Windows curly quotes and dashes work in Helvetica. Characters outside its
  Windows-1252 coverage produce a clear export error; JSON can still be saved.

See `DEVELOPMENT_NOTES.md` for verification details and `BENCHMARK.md` for the
representative timed invoice check. Active work is on `recovered-master-dev`;
the original repository history remains its parent.
