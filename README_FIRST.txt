MEDISCAN AI — SETUP & RUN (WINDOWS)

WHAT'S INCLUDED
- app.py: Streamlit dashboard, searchable report history, saved-report comparison, CSV/PDF exports, and PDF text extraction
- reporting.py: printable A4 PDF report generation with summary, result table, and safety disclaimer
- appointment_prep.py: user-friendly, non-diagnostic questions to discuss with a healthcare professional
- analysis.py: CSV validation, range classification, summaries, and safe comparison of matching saved results
- storage.py: SQLite persistence, report retrieval, and history queries
- tests/: automated tests for validation, classification, and malformed CSV input
- sample_report.csv: synthetic example data
- run_mediscan.bat: Windows launcher
- requirements.txt: runtime and test dependencies

RUN ON WINDOWS
1. Install Python 3.10–3.13 from https://www.python.org/downloads/ and enable the Python launcher.
2. Extract this folder to a normal writable location.
3. Double-click run_mediscan.bat. First-time setup needs internet to install packages.
4. The app should open at http://localhost:8501. If it does not, use the URL printed in the terminal.
5. Keep using the same extracted folder. The .venv folder stores installed packages; do not extract the ZIP again each time. Dependencies are installed only during initial setup (or if an installation is missing/broken).

FOR A PUBLIC ONE-LINK DEMO (RECOMMENDED FOR ORCATHON)
1. Upload these project files to a GitHub repository. Do not upload .venv, secrets, or real patient data.
2. Open https://share.streamlit.io/ and deploy the repository's app.py using its requirements.txt.
3. After deployment succeeds, share the generated web URL. Visitors can open the app in a browser without installing Python or opening Command Prompt.
4. To publish code changes, push/commit the updated files to the connected GitHub branch; Streamlit Community Cloud normally rebuilds/redeploys the app. Verify the live app after each deployment.
5. Use synthetic data only in a public demo. This prototype's SQLite history is not designed for secure multi-user cloud storage; do not upload identifiable patient reports to the hosted demo.

MANUAL SETUP
Open Command Prompt in this folder:
    py -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

RUN TESTS
    .venv\Scripts\python -m pytest -q

CSV FORMAT
Required headers (case-insensitive): test,value,unit,min,max
Each row needs a non-empty test name and unit. value, min, and max must be finite numbers. min must be <= max.
Duplicate/blank headers, missing columns, malformed row widths, missing values, non-numeric values, and invalid ranges are rejected with an error. Values equal to min or max are classified as "In range".
MediScan compares values only to the range supplied in the file; it does not invent or clinically validate reference ranges.

DATABASE / HISTORY
SQLite database mediscan.db is created beside app.py on first launch. Analyze a report and click "Save report to history". Saved reports remain after restarting the app. Compare two saved reports in history: only matching test names with the same units are compared; ambiguous duplicate test/unit rows and unit mismatches are excluded. The numeric difference is not a medical interpretation. Keep/back up mediscan.db to preserve history. Set MEDISCAN_DB_PATH to use a different writable location.
This is local storage, not cloud storage or a multi-user hosted backend.

PDF LIMITATION
PDF support extracts selectable text for manual review only. After a CSV report is analyzed, use Download printable PDF to create a readable A4 report suitable for saving or printing. Saved reports can also be downloaded as PDF. The PDF contains the supplied ranges and a prototype disclaimer; it is not a medical diagnosis. Scanned PDFs need OCR (not included), and arbitrary PDF tables are not automatically converted into structured lab rows.

MEDICAL SAFETY
Hackathon prototype only; not clinically validated. It does not diagnose or prescribe. Use synthetic values for public demos. For real results, consult a qualified healthcare professional. The appointment checklist only helps users prepare questions; it is not a diagnosis or treatment plan.

TROUBLESHOOTING
If package installation fails, check internet/DNS and retry. Do not download packages from unofficial sources. If an old .venv causes import errors, delete it and repeat the manual setup.
