# Invoice workflow benchmark

Use synthetic data to compare workflow speed. The historical target is **2:31**;
the longer-term target is 60–90 seconds. Automated test runtime does not measure
a person's billing time. This cycle has not established a human timing result.

Start timing at the dashboard. Create a new invoice for `Benchmark Client`, dated
`4/30/26`, with a default rate of $250. Enter these four services on each of
`4/1/26`, `4/2/26`, `4/3/26`, and `4/4/26` (16 entries total):

| Description | Hours |
| --- | ---: |
| Review IRS correspondence | 0.50 |
| Telephone conference with client | 0.75 |
| Draft correspondence | 1.00 |
| Prepare response | 1.25 |

Add these costs:

| Description | Quantity | Unit price |
| --- | ---: | ---: |
| Copies | 35 | $0.25 |
| Certified mail | 1 | $9.85 |
| Court filing fee | 1 | $450.00 |

Review and choose Save + Export PDF. Stop timing when the success message
appears. Expected totals: **14.00 hours**, **$3,500.00 services**,
**$468.60 costs**, **$3,968.60 grand total**.

Use Tab to move between entry fields, Enter to add a line, Ctrl+D to prefill the
last entry, and Ctrl+Enter to advance from Services or Costs. Dates remain after
adding. Record elapsed time, mouse clicks, unexpected focus changes, and any
validation interruptions. Repeat once after becoming familiar with the controls.

For a short reliability check, enter dates out of order, edit the first displayed
row, save, reopen, and verify the intended line changed. Save a second invoice
with the same client/date and verify both remain available. Separately try a flat
fee invoice, a long description, and cancelling New Invoice with unsaved edits.
