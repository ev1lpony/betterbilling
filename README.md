# BetterBilling — Recovered Master

This is the consolidated recovery build created after comparing the available
legacy reconstruction, the BetterBilling Git history, the October 2025
speed-first GUI, and the March 2026 JSON/editing refactors.

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

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Core test

```powershell
python tests\test_core.py
```

The GUI requires PySide6. The core tests exercise date parsing, totals, dedupe,
and real PDF generation.
