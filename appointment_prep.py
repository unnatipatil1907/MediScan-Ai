"""Patient-friendly appointment prompts; intentionally non-diagnostic."""
from __future__ import annotations

import pandas as pd


def make_appointment_checklist(results: pd.DataFrame, source_name: str = "Lab report") -> str:
    """Create discussion prompts from flagged rows without diagnosing or recommending treatment."""
    if results is None or results.empty or not {"test", "status", "value", "unit", "min", "max"}.issubset(results.columns):
        raise ValueError("A completed report is needed to prepare questions.")

    lines = [
        "MEDISCAN AI — APPOINTMENT DISCUSSION CHECKLIST",
        f"Report: {source_name}",
        "",
        "Bring the original laboratory report and share any symptoms, medicines, supplements, or fasting details with your healthcare professional.",
        "",
        "QUESTIONS TO CONSIDER",
        "[ ] What do these results mean in the context of my health and symptoms?",
        "[ ] Are the reference ranges and units on this report appropriate for me?",
    ]
    flagged = results[results["status"].isin(["Low", "High"])]
    if not flagged.empty:
        lines.append("")
        lines.append("RESULTS TO DISCUSS")
        for _, row in flagged.iterrows():
            lines.append(f"• {row['test']}: {row['value']:g} {row['unit']} — {row['status']} compared with the supplied range {row['min']:g}–{row['max']:g} {row['unit']}.")
            lines.append(f"  [ ] Ask what this result means for me and whether any follow-up is needed.")
        lines.extend([
            "",
            "[ ] Should any test be repeated or reviewed alongside other results?",
            "[ ] When should I follow up, and what symptoms should prompt urgent medical advice?",
        ])
    else:
        lines.extend([
            "",
            "The listed values fall within the ranges supplied in this file. This does not rule out health concerns.",
            "[ ] Do these results fit my symptoms and health history?",
            "[ ] Is any follow-up needed based on why the tests were ordered?",
        ])
    lines.extend([
        "",
        "This checklist helps prepare a conversation; it is not a diagnosis or treatment plan.",
    ])
    return "\n".join(lines)
