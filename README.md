# Payment Reconciliation System

A seeded, reproducible reconciliation of an INR merchant ledger against delayed, batched bank payouts for October 2026. The project creates synthetic events, writes independent ledger and bank views, plants two known bank-side discrepancies, and checks that the reconciler identifies them and explains the cash bridge.

The app reads the files in `data/` on each request. It does not generate or modify data at startup and has no database, upload, or authentication flow.

## Requirements

- Python 3.11 or newer
- Dependencies listed in `requirements.txt`

Install dependencies from the project root:

```powershell
python -m pip install -r requirements.txt
```

## Run locally

Start the web app:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the HTML report or `http://127.0.0.1:8000/api/report` for JSON. The JSON report represents every money amount as a rupee decimal string; the core calculations use integer paise.

## Generate and validate data

The bundled dataset uses seed `202610`. To reproduce it, including the duplicate and orphan refund, run:

```powershell
python -m recon.generator.cli --seed 202610 --output-dir data --inject
python validate.py --data-dir data
```

The generator writes `ledger.csv`, `payouts.csv`, `payout_lines.csv`, and `ground_truth.json`. `validate.py` checks the planted cases and the expected `IN_TRANSIT`, `PRIOR_PERIOD_SETTLED`, and `OUT_OF_WINDOW` reference sets. The app never runs this generator on boot.

To run the test suite:

```powershell
python -m pytest -q
```

The seed sweep covers seeds `202600` through `202649`, regenerating and validating each dataset.

## Report and reconciliation rules

The report includes the verdict, counts by reason code, an October cash bridge, and one row per exception. Informational items are visually distinguished from actionable items. Validation shows the expected and found planted discrepancies and compares the three cross-month reference sets.

The bridge starts with October ledger net and adjusts for in-transit items, prior-period settlements, overdue items, fee differences, duplicate bank credits, bank-only payments, orphan refunds, duplicate ledger rows, and matched amount differences. Bank net is calculated from payout header `net` values. The residual is bank net minus explained bank net.

## Agreed assumptions

- A transaction is identified only by `txn_ref`, which is unique in the real world. Refunds are separate transactions with their own references and an `original_ref` pointing to the payment.
- There is one merchant and one currency: INR. Core amounts are integer paise; rupee CSV amounts are parsed as `Decimal`. Values with more than two decimal places are rejected. Money is never represented as a float.
- The fee is a flat 2%. The ledger calculates and rounds it half-up per payment transaction. The bank calculates and rounds half-up once per payout using the sum of its positive payment lines. Integer arithmetic implements the fee rounding.
- A refund is a full negative ledger row. It has no fee and does not reverse the original payment fee. Refund lines are not included in the bank fee base.
- Settlement dates use IST. Transactions before 18:00:00 settle T+1 business day; transactions at or after 18:00:00 settle T+2. Business days are Monday through Friday, counted on strictly later calendar dates. Weekend transactions count forward from their transaction date; there are no holidays.
- The reconciliation period is 1–31 October 2026 and is anchored on ledger transaction date. The ledger extract starts 24 September and ends 31 October. Bank payout files contain payouts dated 1–31 October; settlements due in November are absent. October transactions settling after month end are reported as in transit. September transactions settling in October are reported as prior-period settlements; September transactions due before October are out of window.
- Payout header `net` is treated as cash credit. There is no bank statement or third data source. Bank files are trusted for their contents and checked for internal consistency.
- The generator and reconciler are separate implementations. They share settings and exact money helpers, but the generator does not import the reconciler and each side implements its settlement rule independently.

## Fee rounding limitation

For each payout, the reconciler compares expected per-transaction fees with the bank's per-payout fee. It accepts legitimate rounding drift when `2 × |delta| <= n + 1`, where `n` is the payout's positive-line count. A genuine fee error smaller than this tolerance is indistinguishable from rounding drift.

## Data and module layout

- `recon/generator/` creates the event world, ledger view, bank view, and injected cases.
- `recon/reconciler/` loads the three CSVs, checks integrity, matches and classifies rows, calculates fees, builds the bridge, and returns a report.
- `app/` serves the HTML and JSON views.
- `validate.py` compares a report with `ground_truth.json`.
- `data/` contains the deterministic files used by the app.
- `tests/` contains hand-built rule fixtures, generator validation, API tests, and the 50-seed sweep.

## Deploy on Render

The repository includes a Render Blueprint in `render.yaml` and a `.python-version` file selecting Python 3.11. To create the service, push both files to the repository, then in Render choose **New → Blueprint** and connect that GitHub repository. Render reads these settings from the Blueprint:

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Plan | Free |
| Python version | 3.11 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/api/report` |

Render requires web services to bind to `0.0.0.0` and recommends the port in `PORT`. Its free web services have an ephemeral filesystem, so include the generated files under `data/` in the deployed repository and keep the app read-only at runtime. Free services can spin down when idle; the next request may wait for the service to start. See [Render's FastAPI deployment guide](https://render.com/docs/deploy-fastapi) and [free instance details](https://render.com/docs/free).

The service is stateless. A new deploy serves the data contained in that deploy's repository revision.

## Out of scope

Real bank formats, uploads, databases, authentication, multiple merchants, GST, chargebacks, partial refunds, holidays, and subset-sum matching of unlabeled batches are not implemented.
