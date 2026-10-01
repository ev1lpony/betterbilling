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
