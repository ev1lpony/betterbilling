# Recovery audit

## Bottom line

The old project is **not lost** in the sense that matters.

The exact earliest USB `main.py` is still not present, but the Git history
contains a direct evolutionary descendant of its billing engine. The
September/October 2025 code preserves the old invoice model and PDF behavior,
and the March 2026 code adds the durable features we actually want:
JSON persistence, editable invoices, portable storage, per-service rates,
flat fees, and a dashboard.

The right recovery strategy is therefore **merge, not rewrite**.

## Timeline

### Original / Wallace-era CLI
Best known behavior:
- tiny Python/FPDF tool
- service + cost entry
- done/remove/back muscle-memory flow
- dynamic PDF sizing
- 2.5-inch letterhead area
- 15 mm left margin
- service widths 25/80/25/30/30
- cost widths 80/30/30/30
- repeated headers
- very fast invoice completion

### 2025-09-17 — first substantial BetterBilling overhaul
The old engine is still plainly visible:
- same model
- same FPDF design
- same widths/margins/colors
- PySide6 UI added on top

### 2025-09-18 — shell/settings split
- `main.py` becomes app shell/dashboard
- `invoice_create.py` holds billing workflow
- `settings.py` added
- multiple placeholder modules created but left empty

### 2025-10-07 — workflow-fix build
This is the best speed-first GUI baseline:
- long description wrapping
- repeated page headers
- explicit tab order
- Ctrl+D last-entry prefills
- duplicate detection on entry/edit
- review-time dedupe
- editable tables
- unique PDF filenames
- settings-driven default rate/export behavior

### 2026-03-16 — persistence/editing build
Adds:
- project-local portable storage
- JSON invoice files
- Edit Existing Invoice
- overwrite save
- Save As New
- per-service rate editing
- apply default rate to all services
- flat fee support
- dedicated New/Edit dashboard paths

### 2026-03-17 — current refactor
Keeps most March features, but rewrites a large portion of `invoice_create.py`.
Several speed/defensive behaviors disappear or regress.

## Important findings

### Empty files were mostly scaffolding, not lost implementations
Current repo still has empty:
- `db.py`
- `invoice_edit.py`
- `letterheads.py`
- `models.py`
- `pdf_gen.py`
- `utils.py`

The working implementation was never truly split into those modules.
It remained concentrated in `invoice_create.py`.

### Latest is not automatically best
The latest March refactor removed explicit service/cost `setTabOrder(...)`
calls that existed specifically for fast keyboard entry.

It also removed the old `_dedupe_services()` review pass.

### Current sorted-table edit bug
Current service rebuilding sorts for display:
`sorted(self.invoice.services, key=lambda x: x.date)`

But table-edit handling indexes the raw list by table row. If services were
entered out of chronological order, the visual row and underlying list item can
differ.

Recovered Master fixes this with stable per-line IDs.

### Current duplicate-edit validation is weaker than October
October checked a tentative duplicate key before assigning the new value.
The current refactor mutates first, then scans for duplicates. If it detects a
duplicate, rebuilding the table does not automatically restore the old object.

Recovered Master restores validate-before-commit behavior.

### Total hours
The repo tracks total hours in its status display, but `TOTAL HOURS BILLED`
is not present in current PDF generation. The older recovered workflow notes
showed that as a desired invoice output, so it is restored here.

## Recommended base going forward

Use `BetterBilling_Recovered_Master` as the functional recovery branch.

Keep the original repo untouched as archival evidence.

Next development should happen in a new Git branch/repository only after this
build is tested against a few real historical invoices.
