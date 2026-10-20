# BusinessPilot AI — Business Report Generator

Upload business data, check it, see interactive charts, read plain-language insights, forecast revenue honestly, and download
PDF / Word / Excel reports. Built with Streamlit. **All numbers are calculated by code (pandas/NumPy), never by an AI model.**

**Workflow:** Upload → Review → Analyze → Insights → Report → Download (plus Saved analyses).

---
## 1. Install and run (Windows PowerShell)

Requires Python 3.10+ (3.12 tested). From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

(or run `.\setup.ps1` once, then the last command). If scripts are blocked: `Set-ExecutionPolicy -Scope Process Bypass`.
The app opens at http://localhost:8501. Click **Upload → Try demo data** to explore with *synthetic* data.

macOS/Linux: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && streamlit run app.py`

## 2. Optional AI commentary
Copy `.env.example` to `.env` and set `OPENAI_API_KEY=...` (optionally `OPENAI_MODEL`). Restart the app.
* Without a key the app is fully functional; the Insights page says AI is off.
* The AI button sends **only aggregated figures and findings text — no raw rows** — to OpenAI. Nothing is sent unless you click it.
* If the call fails, the app says so; it never claims AI was used when it was not.
* Never commit `.env`. The ZIP contains no keys.

## 3. Optional OCR (images / scanned documents)
`pytesseract` needs the Tesseract program: install from https://github.com/UB-Mannheim/tesseract/wiki and add it to PATH
(or set `pytesseract.pytesseract.tesseract_cmd`). Without it, images are explained as unreadable instead of failing silently.
OCR output is always flagged "please verify". Scanned PDFs: export pages as PNG/JPG and upload those.

## 4. Supported files
| Format | Notes |
|---|---|
| CSV, TXT | Delimiter and encoding auto-detected. TXT must look like a table. |
| XLSX / XLS | All sheets are stacked (a `sheet` column is added). `.xls` needs `xlrd` (in requirements). |
| JSON | List of records, or an object holding such a list. |
| PDF | Text-based PDFs: tables extracted; otherwise text-layout reconstruction (flagged to verify). |
| DOCX | Tables inside the document. **.doc** cannot be read reliably — save as .docx. |
| PNG/JPG/WEBP | OCR (needs Tesseract). |
| Manual | Type rows or paste CSV. |

Limits (editable in `.env`): 25 MB/file, 10 files, 500,000 rows, 60 PDF pages. Files are checked by extension **and** content signature.
Uploaded content is only ever treated as data — never executed, and text inside files is never followed as instructions.

## 5. Features
* **Home** with Start New Analysis / Upload, recent saved analyses, demo data.
* **Upload center** with per-file status, OCR notice, manual entry.
* **Review**: preview, quality score, blank/duplicate/negative/unparseable checks, **editable column mapping**, "what can be analyzed".
* **Dashboard**: only metrics supported by your data (revenue, expenses, gross/net profit, margin, growth, units, customers, repeat rate,
  concentration, order value, marketing ROAS/CPA/CTR/conversion, stock, stock cover) with tooltips (meaning + formula + period/assumptions);
  filters for date, product, category; trend, quarterly/monthly sales, products, expenses, customers, actual-vs-predicted charts (Plotly).
* **Insights**: summary, findings, positives, risks, anomalies, likely factors, recommendations, next steps, limitations.
  Each line is labelled *Verified calculation / Observed trend / Interpretation / Forecast*.
* **Forecasting**: needs 12+ complete months. Candidates (naive, 3-period mean, linear trend, damped Holt, seasonal naive, seasonal+yearly change)
  are compared by **rolling-origin back-testing** (each forecast uses only earlier data); an 80% *empirical prediction interval* comes from
  out-of-sample errors. Shows MAE/RMSE/MAPE, comparison with the naive baseline, assumptions and limitations. What-if scenario slider is labelled as not a prediction.
  Risk indicators are rule-based and not probabilities. The optional event-probability tool trains a logistic model on a labelled outcome
  column with a chronological split when dates exist, and reports Brier score against a baseline.
* **Reports**: 10 types, automatic recommendation or manual choice, section picker, preview, PDF/DOCX/XLSX from the same content
  (charts embedded; Excel has formatted sheets and a native chart). Empty reports are refused; failures are shown, never hidden.
* **Saved analyses** (SQLite + files in `data/`): reopen, rename, delete (with confirmation), re-download stored reports.
  Stored **locally on the machine running the app**, with no accounts — do not host publicly with sensitive data.
  Starting a new analysis asks before discarding unsaved work.

### Metric definitions
Net profit = Revenue − COGS − Expenses (or the provided profit column if no costs). Profit margin = Net profit ÷ Revenue.
Growth = (latest − previous complete month) ÷ previous; a month that ends mid-month is excluded. Repeat rate = customers with 2+ orders ÷ customers.
ROAS = Revenue ÷ marketing spend. Quality score = 100 minus penalties for blanks, duplicates and unreadable values.
Blank or unreadable cells are excluded and reported — never zero-filled or guessed.

## 6. Project layout
```
app.py                    Streamlit entry point + navigation
businesspilot/
  config.py               limits, env access        ingestion.py   validation, extraction, OCR
  schema.py               column detection/mapping  metrics.py     all calculations
  forecasting.py          forecasts, risk           prediction.py  probability model (+ re-exports)
  ai_insights.py          rule-based + optional LLM charts.py      Plotly figures
  report_charts.py        matplotlib charts (files) reports.py     build + PDF/DOCX/XLSX
  pipeline.py             one-call analysis         db.py          SQLite persistence
  demo.py                 synthetic demo data       io_utils.py    legacy wrappers
  ui/                     theme, state, pages
tests/                    85 tests (unittest)
```

## 7. Testing
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```
Covers calculations, validation, CSV/Excel/JSON/TXT/DOCX/PDF/OCR loading, malformed data, AI fallback, forecasting (incl. leakage and
insufficient data), PDF/DOCX/XLSX generation (re-opened and checked), database operations, and page flows.
`tests/test_app_real_streamlit.py` drives the real app with Streamlit's AppTest (runs only where Streamlit is installed).
When Streamlit is absent, `test_app_smoke.py` runs page code against a stand-in (`tests/fake_streamlit.py`) — that checks logic and data flow,
**not** real rendering or Streamlit API compatibility.

## 8. Troubleshooting
* *Charts don't show*: `pip install -r requirements.txt` (plotly). *"ModuleNotFoundError"*: run with the venv's python as above.
* *OCR says unavailable*: install Tesseract and restart the terminal.
* *Dates misread / future dates*: check day/month order in your file; the Review page lists unreadable values.
* *No forecast*: needs 12+ complete months of revenue with dates; the page states exactly what is missing.
* *Wrong metrics*: fix the column mapping on **Review**. *Port busy*: `streamlit run app.py --server.port 8502`.
* *Saved data location*: `data/` (change with `BP_DATA_DIR`).

## 9. Known limitations
* Not an accounting system; verify important figures. Forecasts assume recent patterns continue.
* PDF/OCR table reconstruction can be imperfect (flagged). Legacy `.doc` unsupported.
* Single-user local app: no login, no multi-tenant isolation or encryption at rest.
* Currency is a label only (no conversion).
