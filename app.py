from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
from analysis import REQUIRED, validate_and_analyze, make_summary, read_csv_bytes, compare_reports
from storage import DB_PATH, db_connect, init_db, save_report, get_history, get_report
from reporting import build_pdf_report
from appointment_prep import make_appointment_checklist

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import fitz  # PyMuPDF: render scanned PDF pages for OCR
    import pytesseract
    from PIL import Image
except ImportError:
    fitz = None
    pytesseract = None
    Image = None

APP_VERSION = "2.5"

st.set_page_config(page_title="MediScan AI", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #f5f8fc; }
.block-container { max-width: 1440px; padding-top: 1.3rem; padding-bottom: 3rem; }
[data-testid="stSidebar"] { background: #10243a; }
[data-testid="stSidebar"] * { color: #f0f5fc !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #d4e1f0 !important; }
.hero { background: linear-gradient(120deg,#10243a 0%,#164e78 55%,#2776c8 100%); padding: 30px 34px; border-radius: 22px; color: white; box-shadow: 0 12px 30px rgba(20,60,100,.14); margin-bottom: 22px; }
.hero h1 { font-family: 'Manrope', sans-serif; font-size: 2.35rem; line-height: 1.12; margin: 0 0 10px 0; color: #fff; }
.hero p { font-size: 1rem; max-width: 820px; color: #e2efff; margin: 0; }
.eyebrow { text-transform: uppercase; letter-spacing: .16em; font-size: .73rem; font-weight: 700; color: #a7d5ff; margin-bottom: 10px; }
.section-title { font-family: 'Manrope', sans-serif; font-size: 1.25rem; font-weight: 800; color: #12283f; margin: 8px 0 3px; }
.subtle { color: #60758b; font-size: .91rem; }
.panel { background: white; border: 1px solid #e0e9f3; border-radius: 17px; padding: 18px 20px; }
div[data-testid="stMetric"] { background: white; border: 1px solid #e0e9f3; padding: 16px 18px; border-radius: 16px; box-shadow: 0 3px 10px rgba(20,50,80,.025); }
div[data-testid="stMetricLabel"] { color: #5d7187; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] { border-radius: 11px; min-height: 2.8rem; font-weight: 700; }
div[data-testid="stDataFrame"] { border: 1px solid #e0e9f3; border-radius: 13px; overflow: hidden; }
div[data-testid="stAlert"] { border-radius: 12px; }
hr { border-color: #e0e9f3; }
</style>
""", unsafe_allow_html=True)


def extract_uploaded_document(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Extract selectable PDF text, OCR scanned PDF pages, or OCR an image.

    Returns (extracted_text, method_used). OCR text must be checked against the
    original report; this function does not create trusted structured lab rows.
    """
    suffix = Path(filename).suffix.lower()
    if pytesseract is None or Image is None or fitz is None:
        raise RuntimeError("OCR dependencies are not installed. Check requirements.txt and packages.txt, then redeploy.")

    try:
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
            image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            text = pytesseract.image_to_string(image, config="--psm 6")
            return text.strip(), "OCR from image"

        if suffix != ".pdf":
            raise ValueError("Unsupported file type. Upload a PDF, PNG, or JPG image.")

        # Prefer embedded/selectable text when present.
        selectable_text = ""
        if PdfReader is not None:
            reader = PdfReader(io.BytesIO(file_bytes))
            selectable_text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if len(selectable_text) >= 30:
            return selectable_text, "Selectable PDF text"

        # If the PDF is scanned (or has almost no selectable text), render pages and OCR them.
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_texts = []
        for page_number, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            page_text = pytesseract.image_to_string(image, config="--psm 6").strip()
            if page_text:
                page_texts.append(f"--- Page {page_number} ---\n{page_text}")
        doc.close()
        return "\n\n".join(page_texts).strip(), "OCR from scanned PDF"
    except RuntimeError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read this file: {exc}") from exc


def render_analysis(df: pd.DataFrame, source_name: str, source_type: str, raw_bytes: bytes):
    summary = make_summary(df)
    st.markdown('<div class="section-title">Report overview</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    low_count = int((df.status == "Low").sum())
    in_count = int((df.status == "In range").sum())
    high_count = int((df.status == "High").sum())
    a.metric("Tests analyzed", len(df))
    b.metric("Low", low_count)
    c.metric("In range", in_count)
    d.metric("High", high_count)

    # Transparent, deterministic insights: no diagnosis or invented reference ranges.
    st.markdown('<div class="section-title">Report checks</div>', unsafe_allow_html=True)
    st.success("We checked the file for missing information, invalid numbers, and reversed reference ranges. Please still confirm the values against your original report.")

    st.markdown('<div class="section-title">Smart report insights</div>', unsafe_allow_html=True)
    chart_col, insight_col = st.columns([1, 1.25])
    with chart_col:
        st.caption("Result distribution")
        st.bar_chart(pd.DataFrame({"Results": [low_count, in_count, high_count]}, index=["Low", "In range", "High"]))
    with insight_col:
        st.caption("What this report shows")
        st.write(f"**{len(df)}** test result(s) compared with the ranges supplied in this file.")
        if low_count or high_count:
            st.write(f"**{low_count + high_count}** result(s) fall outside their supplied ranges and may be worth reviewing with a qualified healthcare professional.")
            flagged = df[df["status"] != "In range"]
            st.dataframe(flagged[["test", "value", "unit", "min", "max", "status"]], use_container_width=True, hide_index=True)
        else:
            st.write("All listed values fall within the supplied reference ranges. This does not rule out health concerns.")
    st.markdown('<div class="section-title">Detailed result review</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "value": st.column_config.NumberColumn("Result", format="%.4g"),
        "min": st.column_config.NumberColumn("Reference min", format="%.4g"),
        "max": st.column_config.NumberColumn("Reference max", format="%.4g"),
    })
    st.markdown('<div class="section-title">Plain-language summary</div>', unsafe_allow_html=True)
    st.info(summary)

    st.markdown('<div class="section-title">Prepare for a healthcare visit</div>', unsafe_allow_html=True)
    st.write("Use these questions to help discuss the report with a qualified healthcare professional.")
    checklist = make_appointment_checklist(df, source_name)
    with st.expander("View discussion checklist", expanded=bool(low_count or high_count)):
        st.text(checklist)
    st.download_button("Download appointment checklist", data=checklist.encode("utf-8"),
                       file_name="mediscan_appointment_checklist.txt", mime="text/plain", use_container_width=False)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.download_button("Download analyzed CSV", data=df.to_csv(index=False).encode("utf-8"),
                           file_name="mediscan_analyzed_results.csv", mime="text/csv", use_container_width=True)
    with col2:
        try:
            pdf_bytes = build_pdf_report(df, source_name, summary)
            st.download_button("Download printable PDF", data=pdf_bytes,
                               file_name="mediscan_printable_report.pdf", mime="application/pdf", use_container_width=True)
        except Exception as exc:
            st.error("We couldn't create the printable report. Please try again or download the CSV results.")
    with col3:
        if st.button("Save report to history", type="primary", use_container_width=True):
            try:
                report_id = save_report(df, source_name, source_type, raw_bytes, summary)
                st.session_state["last_saved_id"] = report_id
                st.success("Report saved. You can find it later in Saved history.")
            except sqlite3.Error:
                st.error("We couldn't save this report. Please try again. Your current analysis is still available on this screen.")

# Apply navigation requests before the keyed radio widget is created. Streamlit
# forbids changing a widget's own session-state key after instantiation.
if "NAVIGATION_REQUEST" in st.session_state:
    requested_page = st.session_state.pop("NAVIGATION_REQUEST")
    if requested_page in ["Dashboard", "Analyze report", "Saved history", "About & limitations"]:
        st.session_state["NAVIGATION"] = requested_page

init_db()
with st.sidebar:
    st.markdown("## 🩺 MediScan AI")
    st.caption("REPORT INTELLIGENCE • HACKATHON EDITION")
    if "NAVIGATION" not in st.session_state:
        st.session_state["NAVIGATION"] = "Dashboard"
    page = st.radio("NAVIGATION", ["Dashboard", "Analyze report", "Saved history", "About & limitations"],
                    key="NAVIGATION", label_visibility="visible")
    st.divider()
    try:
        saved_count = len(get_history())
    except Exception:
        saved_count = 0
    st.metric("Saved reports", saved_count)
    st.caption("Your saved reports stay on this computer.")

st.markdown("""
<div class="hero">
  <div class="eyebrow">Orcathon · Healthcare data clarity</div>
  <h1>Understand the numbers.<br>Review with confidence.</h1>
  <p>MediScan AI organizes lab values into transparent reference-range checks, explainable flags, and a saved report history. Designed for careful review — not diagnosis.</p>
</div>
""", unsafe_allow_html=True)
st.info("MediScan helps you review lab values; it does not diagnose. Check results against your original report and discuss concerns with a healthcare professional.")

if page == "Dashboard":
    history = get_history()
    total_reports = len(history)
    total_tests = int(history.total_tests.sum()) if total_reports else 0
    high = int(history.high_count.sum()) if total_reports else 0
    low = int(history.low_count.sum()) if total_reports else 0
    a,b,c,d = st.columns(4)
    a.metric("Saved reports", total_reports)
    b.metric("Tests processed", total_tests)
    c.metric("Low flags in history", low)
    d.metric("High flags in history", high)
    st.markdown('<div class="section-title">Your report workspace</div>', unsafe_allow_html=True)
    st.markdown('<p class="subtle">Review a lab report, understand which values are outside the supplied ranges, and prepare questions for your healthcare visit.</p>', unsafe_allow_html=True)
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Understand your report**")
        st.write("01 · Review each test beside its supplied reference range")
        st.write("02 · See which results are below, within, or above that range")
        st.write("03 · Download a printable report and discussion checklist")
        st.write("04 · Save reports to review them again later")
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Tools to help you**")
        st.write("✓ Try a sample report before uploading your own")
        st.write("✓ Compare saved reports from different dates")
        st.write("✓ Download a PDF for printing or sharing")
        st.write("✓ Prepare questions for your healthcare professional")
        st.markdown('</div>', unsafe_allow_html=True)
    if st.button("Open report analyzer", type="primary"):
        # Use a separate request key; apply it on the next run before st.radio.
        st.session_state["NAVIGATION_REQUEST"] = "Analyze report"
        st.rerun()

elif page == "Analyze report":
    st.markdown('<div class="section-title">Choose your input</div>', unsafe_allow_html=True)
    demo_tab, csv_tab, pdf_tab = st.tabs(["✨ Synthetic demo", "📄 CSV upload", "📑 PDF / image OCR"])
    with demo_tab:
        st.caption("All values below are synthetic and are for demonstration only.")
        demo = pd.DataFrame([
            {"test":"Hemoglobin","value":10.2,"unit":"g/dL","min":12,"max":16},
            {"test":"White Blood Cells","value":7.1,"unit":"10^3/uL","min":4,"max":11},
            {"test":"Platelets","value":250,"unit":"10^3/uL","min":150,"max":400},
            {"test":"Fasting Glucose","value":128,"unit":"mg/dL","min":70,"max":99},
            {"test":"Vitamin B12","value":190,"unit":"pg/mL","min":200,"max":900},
            {"test":"Creatinine","value":0.9,"unit":"mg/dL","min":0.6,"max":1.2},
        ])
        st.dataframe(demo, use_container_width=True, hide_index=True)
        if st.button("Process synthetic demo", type="primary", key="demo_process"):
            try:
                result = validate_and_analyze(demo)
                st.session_state["current_result"] = result
                st.session_state["current_source_name"] = "Synthetic demo report"
                st.session_state["current_source_type"] = "synthetic"
                st.session_state["current_raw_bytes"] = demo.to_csv(index=False).encode()
                st.success("Synthetic report processed.")
            except ValueError as exc:
                st.error(str(exc))
    with csv_tab:
        with st.expander("What kind of file can I upload?"):
            st.write("Choose a CSV table with one row per test and these columns: test name, result, unit, minimum reference value, and maximum reference value. Each result and range must be numeric.")
            st.download_button("Download sample CSV", data=Path(__file__).with_name("sample_report.csv").read_bytes(),
                               file_name="sample_report.csv", mime="text/csv")
        upload = st.file_uploader("Select CSV report", type=["csv"], key="csv_file")
        st.caption("Results update automatically when you upload or replace the CSV file.")
        if upload is not None:
            raw = upload.getvalue()
            # Streamlit reruns the app when the uploaded file changes. Hash the bytes
            # so we only re-analyze when the content actually changes.
            import hashlib
            upload_signature = hashlib.sha256(raw).hexdigest()
            if st.session_state.get("processed_csv_signature") != upload_signature:
                try:
                    result = validate_and_analyze(read_csv_bytes(raw))
                    st.session_state["current_result"] = result
                    st.session_state["current_source_name"] = upload.name
                    st.session_state["current_source_type"] = "csv"
                    st.session_state["current_raw_bytes"] = raw
                    st.session_state["processed_csv_signature"] = upload_signature
                    st.success(f"Automatically analyzed {upload.name}.")
                except ValueError as exc:
                    st.session_state.pop("processed_csv_signature", None)
                    st.error(str(exc))
                except Exception:
                    st.session_state.pop("processed_csv_signature", None)
                    st.error("We couldn't process this file. Check that it is a valid CSV and try again. If the problem continues, use the sample file.")
    with pdf_tab:
        st.write("Upload a PDF or a clear photo of a lab report. Scanned pages and images are read with OCR. The extracted text is for manual review and is not automatically converted into trusted lab results.")
        document_upload = st.file_uploader("Select a PDF or report image", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"], key="pdf_file")
        if st.button("Extract text with OCR", type="primary"):
            if document_upload is None:
                st.error("Choose a PDF or image before clicking Extract text with OCR.")
            else:
                try:
                    extracted, extraction_method = extract_uploaded_document(document_upload.getvalue(), document_upload.name)
                    if extracted:
                        st.session_state["pdf_text"] = extracted
                        st.session_state["pdf_extraction_method"] = extraction_method
                        st.success(f"Text extracted using: {extraction_method}. Please check every value against the original report.")
                    else:
                        st.session_state.pop("pdf_text", None)
                        st.warning("No text could be recognized. Try a sharper, well-lit image with the full page visible, or upload a clearer PDF.")
                except (ValueError, RuntimeError) as exc:
                    st.error(f"Could not extract text: {exc}")
        if st.session_state.get("pdf_text"):
            st.caption(st.session_state.get("pdf_extraction_method", "Extracted text") + " · OCR may misread decimals, units, and test names.")
            st.text_area("Extracted text — verify against original", value=st.session_state["pdf_text"], height=300)
            st.download_button("Download extracted text", data=st.session_state["pdf_text"].encode("utf-8"), file_name="mediscan_extracted_text.txt", mime="text/plain")
    if st.session_state.get("current_result") is not None:
        st.divider()
        render_analysis(st.session_state["current_result"], st.session_state["current_source_name"],
                        st.session_state["current_source_type"], st.session_state["current_raw_bytes"])

elif page == "Saved history":
    st.markdown('<div class="section-title">Saved report history</div>', unsafe_allow_html=True)
    st.caption("Your saved reports stay on this computer and remain available after you close the app.")
    history = get_history()
    if history.empty:
        st.info("No saved reports yet. Analyze a report and click Save report to history.")
    else:
        search_text = st.text_input("Search saved reports", placeholder="Search by filename or source type")
        filtered_history = history.copy()
        if search_text.strip():
            query = search_text.strip().casefold()
            filtered_history = filtered_history[filtered_history.apply(
                lambda row: query in str(row["source_name"]).casefold() or query in str(row["source_type"]).casefold(), axis=1)]
        history_view = filtered_history.rename(columns={
            "source_name": "Report file", "created_at": "Saved on", "total_tests": "Tests",
            "low_count": "Low", "in_range_count": "In range", "high_count": "High",
            "source_type": "Input type", "id": "_report_id"
        })
        visible_cols = [c for c in ["Report file", "Saved on", "Tests", "Low", "In range", "High"] if c in history_view.columns]
        st.dataframe(history_view[visible_cols], use_container_width=True, hide_index=True)
        if len(filtered_history) >= 2:
            with st.expander("Compare two saved reports", expanded=False):
                st.caption("Compare matching test names with the same units. This shows numeric changes only; it does not decide whether a change is medically good or bad.")
                compare_ids = filtered_history["id"].astype(int).tolist()
                labels = {int(row.id): f"#{int(row.id)} · {row.source_name} · {row.created_at}" for row in filtered_history.itertuples()}
                old_col, new_col = st.columns(2)
                with old_col:
                    previous_id = st.selectbox("Earlier report", compare_ids, index=min(1, len(compare_ids)-1), format_func=lambda x: labels[x], key="compare_previous_id")
                with new_col:
                    current_id = st.selectbox("Report to compare", compare_ids, index=0, format_func=lambda x: labels[x], key="compare_current_id")
                if previous_id == current_id:
                    st.info("Choose two different reports to compare.")
                else:
                    previous_record, previous_rows = get_report(previous_id)
                    current_record, current_rows = get_report(current_id)
                    comparison, ambiguous_tests = compare_reports(previous_rows, current_rows)
                    if not comparison.empty:
                        st.dataframe(comparison, use_container_width=True, hide_index=True, column_config={
                            "previous_value": st.column_config.NumberColumn("Earlier result", format="%.4g"),
                            "current_value": st.column_config.NumberColumn("Later result", format="%.4g"),
                            "change": st.column_config.NumberColumn("Numeric change", format="%+.4g"),
                        })
                        st.download_button("Download comparison CSV", data=comparison.to_csv(index=False).encode("utf-8"),
                                           file_name=f"mediscan_comparison_{previous_id}_to_{current_id}.csv", mime="text/csv", key="download_comparison")
                    else:
                        st.warning("No unambiguous matching tests with the same units were found in both reports.")
                    if ambiguous_tests:
                        st.warning("Skipped repeated test/unit entries because they could not be matched safely: " + ", ".join(ambiguous_tests))
                    old_only = set(previous_rows["test"].astype(str).str.casefold()) - set(current_rows["test"].astype(str).str.casefold())
                    new_only = set(current_rows["test"].astype(str).str.casefold()) - set(previous_rows["test"].astype(str).str.casefold())
                    if old_only or new_only:
                        st.caption(f"Some tests appear in only one report ({len(old_only)} only in the earlier report; {len(new_only)} only in the later report). Unit mismatches are also excluded from comparison.")
        if filtered_history.empty:
            st.info("No saved reports match that search.")
            st.stop()
        ids = filtered_history["id"].astype(int).tolist()
        selected_id = st.selectbox("Open a saved report", ids, format_func=lambda x: f"Report #{x} · {filtered_history.loc[filtered_history.id == x, 'source_name'].iloc[0]}")
        report, rows = get_report(selected_id)
        if report:
            st.markdown(f"**{report['source_name']}** · Saved {report['created_at']}")
            a,b,c,d = st.columns(4)
            a.metric("Tests", report["total_tests"])
            b.metric("Low", report["low_count"])
            c.metric("In range", report["in_range_count"])
            d.metric("High", report["high_count"])
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.info(report["summary"])
            export_col1, export_col2 = st.columns(2)
            with export_col1:
                st.download_button("Download saved CSV", data=rows.to_csv(index=False).encode(),
                                   file_name=f"mediscan_report_{selected_id}.csv", mime="text/csv", use_container_width=True)
            with export_col2:
                saved_pdf = build_pdf_report(rows, report["source_name"], report["summary"],
                                             created_at=report["created_at"], report_id=int(selected_id))
                st.download_button("Download saved PDF", data=saved_pdf,
                                   file_name=f"mediscan_report_{selected_id}.pdf", mime="application/pdf", use_container_width=True)
            with st.expander("Delete saved report"):
                st.warning("This permanently deletes this report and its result rows from this local database.")
                confirm = st.checkbox(f"Confirm deletion of report #{selected_id}", key=f"del_{selected_id}")
                if st.button("Delete report permanently", disabled=not confirm):
                    with db_connect() as conn:
                        conn.execute("DELETE FROM reports WHERE id=?", (int(selected_id),))
                    st.success("Report deleted.")
                    st.rerun()

else:
    st.markdown('<div class="section-title">About MediScan AI</div>', unsafe_allow_html=True)
    st.write("MediScan helps you organize laboratory results and compare each value with the reference range supplied in the same report.")
    st.markdown("**Please keep in mind**")
    st.write("- A Low or High flag is not a diagnosis. Your health history, symptoms, and the laboratory's guidance all matter.")
    st.write("- MediScan does not decide whether a reference range is medically correct and does not recommend treatment.")
    st.write("- Always compare the results with your original laboratory report and ask a qualified healthcare professional about concerns.")
    st.markdown("**Your privacy**")
    st.write("When you choose Save report, the report is stored on this computer so you can open it later. Avoid using identifiable patient information on a shared computer. Delete saved reports when you no longer need them.")
    st.markdown("**Using PDF files**")
    st.write("MediScan can extract selectable text from some PDFs for you to review. It may not preserve table layout, and scanned PDFs may not work. Check extracted text carefully; CSV upload is the supported analysis workflow.")
