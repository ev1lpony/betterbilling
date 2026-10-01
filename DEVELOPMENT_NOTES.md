# Stabilization cycle — October 1, 2026

The recovered workspace is the source of truth. It initially had no `.git`.
The confirmed remote is `https://github.com/ev1lpony/betterbilling.git`; its main
tip was `3a3cb6f5bb939d05bb8487029e830296ffaa30f1`, matching the handoff history.
The new `recovered-master-dev` line retains that commit as ancestry. Snapshot
`e9937c2` records the recovered source before implementation. Historical files
absent from the recovered workspace remain accessible in the parent history.

## Changes

`models.py`, `storage.py`, and `settings.py` reject silent record corruption,
preserve valid legacy data, repair imported line identities, constrain filenames
to the intended storage folders, and protect saves with staging/recovery.
Malformed settings stay intact on read and receive an ignored recovery copy
before an explicit replacement. Settings changes make one atomic write.

`main.py` protects unsaved work, preserves imported range/precision, validates
inline edits before committing, retains service dates, restores entry focus,
and adds Ctrl+Enter page advancement. Generated amount cells are read-only.
An unfinished service/cost form remains unsaved after Save; only added rows are
part of the invoice record. Filename errors produce actionable Review feedback.

`pdf_gen.py` retains US Letter, Helvetica, historical column widths/colors,
15 mm left margin, and the 2.5-inch first-page reservation. Real font measurement
now sizes/wraps descriptions, splits tall rows, repeats headers, and keeps large
totals within the page. Typical mixed invoices fit at a readable 10–14 pt size.

The launcher reports setup/start errors and repairs a missing dependency in an
existing environment. `.gitignore` excludes all data folders, private settings,
recovery copies, virtual environments, test artifacts, and caches.

## Verification

The baseline suite passed 3 tests under normal Windows filesystem access. The
old documented direct test command failed because the project root was missing
from its import path; that command is repaired. The earlier `TEST_RESULTS.txt`
described a different runtime and did not verify this Windows installation.

The expanded suite uses synthetic records and temporary storage only. It covers
dates, normalization, totals, flat/mixed fees, rate propagation, duplicate
editing/review cleanup, stable IDs, old JSON, malformed data, filenames,
collisions, atomic save failures/rollback, settings migration, and Qt keyboard
entry/navigation. PDF tests inspect real extracted content, font/page geometry,
headers, row preservation, and border/text bounds.

Poppler renders were inspected for a typical mixed invoice, tall flat/service/
cost descriptions, Windows punctuation, and extreme totals. Synthetic files and
renders remain ignored under `.test-artifacts/pdf-qa/`.

The Windows app launched and its dashboard was observed through accessibility.
The native desktop helper reported capture timeouts and an input/foreground
error, so native end-to-end input verification was incomplete. Qt offscreen
tests exercise real key events and major workflows. Hands-on timing/focus and
the actual office printer/PDF viewer remain the product owner's checks.

Tested environment: Python 3.13.13, PySide6 6.11.2, fpdf2 2.8.9, pytest 9.1.1,
pypdf 6.19.0. The project-local `.venv` is ready for testing.

## Limits

Two distinct files cannot be replaced atomically together across sudden process
termination or power loss. Each file replacement is atomic; ordinary rendering,
backup, and replacement failures are tested, with original recovery copies kept
if rollback itself fails. Core invoicing remains local and works offline.
New saves also refuse collisions appearing after filename allocation. Windows
uses exclusive rename, including on FAT/exFAT portable drives; the non-Windows
implementation requires filesystem hardlink support.

Helvetica supports Windows-1252 text. Unsupported characters produce an export
error without replacing saved files; JSON supports Unicode. Monetary arithmetic
and the recovered JSON schema remain unchanged. No human 2:31 timing claim has
been made. Packaging, licensing, clients, and cloud features remain future work.

Final automated checks: **199 tests passed in 8.33 seconds**, source/test byte
compilation passed, dependency consistency passed, and `git diff --check` passed.
The documented direct core test command also passed its 3 tests.

## Compact interface and practical Help — October 1, 2026

The approved Compact direction now uses a narrow, vertical entry column beside
the service/cost table. Add sits below the last field; mouse entry stays in one
column. The description column receives spare table width and numeric cells
align right. Existing handlers, stable IDs, invoice steps, date retention,
Tab/Enter/Ctrl+D/Ctrl+Enter behavior, save operations, and the PDF layout remain
in place. Flat fee fields appear when their checkbox is selected.

`ui_theme.py` centralizes the neutral palette, type, focus states, and controls.
Small SVG carets and checkmarks under `assets/ui` keep number controls and
checkbox states visible. Their paths resolve from the module, including when
the portable folder moves. `help_ui.py` provides six offline topics with
current control names and worked examples. Help opens modelessly to the current
step and returns focus/selection without mutating the draft. The Review screen
escapes user text, presents readable tables, and keeps totals outside the
scrolling content. Save and export messages use familiar names, with full paths
available in details.

Qt renders with synthetic records were inspected at 1200×800 and 1000×700 for
Home, Details, Services, Costs, Review, Settings, and Help. Test-only font
registration uses installed Segoe UI files because the offscreen Qt plugin
does not discover Windows fonts. No user billing data is used for QA.

Automated verification: **234 tests passed in 12.59 seconds**, including 100 Qt
GUI cases and 15 independent Help cases. New regressions cover vertical field
geometry, Add proximity, column sizing, focus/selection preservation, F1 topic
selection, literal rich text, small-window Review totals, flat fee visibility,
mouse clicks on styled number arrows, and mouse Help preserving text selection.
Draft recovery, invoice search, and embedded PDF preview remain proposals for
the user to approve; they were not added during this design pass.
