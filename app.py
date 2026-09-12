import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from careloop_agent import run_careloop


DATA_PATH = Path(__file__).parent / "data" / "demo_patient.json"

st.set_page_config(
    page_title="CareLoop",
    page_icon="✓",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {max-width: 1180px; padding-top: 2.5rem; padding-bottom: 4rem;}
        [data-testid="stMetric"] {
            background: rgba(128, 128, 128, 0.06);
            border: 1px solid rgba(128, 128, 128, 0.18);
            border-radius: 0.75rem;
            padding: 0.8rem 1rem;
        }
        div.stButton > button[kind="primary"] {
            min-height: 3.25rem;
            font-size: 1.05rem;
            font-weight: 650;
        }
        .completed-note {opacity: 0.62;}
    </style>
    """,
    unsafe_allow_html=True,
)


def load_demo_chart():
    return json.loads(DATA_PATH.read_text())


def format_visit(value):
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y at %I:%M %p")
    except (TypeError, ValueError):
        return value


chart = load_demo_chart()
patient = chart["patient"]
plan_by_id = {
    item["id"]: item["text"] for item in chart["previous_visit"]["plan_items"]
}

st.title("CareLoop")
st.subheader("Pre-visit care-plan loop closure")
st.info("🧪 This demo uses synthetic patient data. No real patient information is shown.")

patient_columns = st.columns(4)
patient_columns[0].metric("Patient", patient["name"])
patient_columns[1].metric("Age", patient["age"])
patient_columns[2].metric("Visit type", patient["visit_type"])
patient_columns[3].metric(
    "Upcoming visit", format_visit(patient["upcoming_visit"])
)

st.write("")
run_clicked = st.button(
    "Run CareLoop",
    type="primary",
    use_container_width=True,
    disabled="careloop_results" in st.session_state,
)

if run_clicked and "careloop_results" not in st.session_state:
    try:
        with st.spinner("Verifying prior care-plan items…"):
            st.session_state.careloop_results = run_careloop(str(DATA_PATH))
    except Exception as exc:
        st.error(f"CareLoop could not complete the review: {exc}")

if "careloop_results" not in st.session_state:
    st.caption("Run CareLoop to verify each prior plan item before the visit.")
else:
    output = st.session_state.careloop_results
    results = output["results"]
    tasks = output["staff_tasks"]
    source_records = output["source_records"]
    completed = sum(item["status"] == "COMPLETED" for item in results)
    unresolved = len(results) - completed

    st.divider()
    st.header("Review Summary")
    summary_columns = st.columns(4)
    summary_columns[0].metric("Total plan items", len(results))
    summary_columns[1].metric("Documented complete", completed)
    summary_columns[2].metric("Needs review", unresolved)
    summary_columns[3].metric("Draft staff tasks", len(tasks))

    st.info(
        "Assessment is limited to the supplied records. "
        "Not documented does not mean not done."
    )

    st.subheader("Plan Items")
    for item in results:
        is_completed = item["status"] == "COMPLETED"
        with st.container(border=True):
            heading = plan_by_id.get(item["item_id"], item["item_id"])
            if is_completed:
                st.markdown(
                    f'<div class="completed-note"><strong>{heading}</strong></div>',
                    unsafe_allow_html=True,
                )
                st.caption("✓ DOCUMENTED COMPLETE")
            else:
                st.markdown(f"#### ⚠️ {heading}")
                st.warning(f"NEEDS REVIEW · {item['status']}", icon="⚠️")

            checked_categories = ", ".join(
                item["record_categories_checked"]
            )
            st.caption(f"Evidence checked: {checked_categories}")

            detail_columns = st.columns([1, 1])
            with detail_columns[0]:
                st.markdown("**Evidence summary**")
                st.write(item["evidence_summary"])
            with detail_columns[1]:
                st.markdown("**Reason**")
                st.write(item["reason"])

            source_ids = item.get("source_ids", [])
            if source_ids:
                with st.expander("View source evidence"):
                    for source_id in source_ids:
                        source = source_records[source_id]
                        record = source["record"]
                        st.markdown(f"**{source_id}**")
                        st.caption(
                            source["record_category"]
                            .replace("_", " ")
                            .title()
                        )
                        for key, value in record.items():
                            if key != "source_id":
                                label = key.replace("_", " ").title()
                                st.markdown(f"- **{label}:** {value}")
            else:
                with st.expander("View source evidence"):
                    st.caption(
                        "No positive source record documents completion "
                        "in the supplied evidence."
                    )

    st.header("Staff Tasks")
    if not tasks:
        st.success("No staff follow-up tasks were created.")
    else:
        for index, task in enumerate(tasks, start=1):
            with st.container(border=True):
                st.markdown(f"**{index}. {task['task']}**")
                st.caption(f"{task['status']}  ·  Plan item: {task['item_id']}")
                st.write(task["plan_item"])

st.divider()
st.caption(
    "CareLoop verifies documented care-plan completion. "
    "It does not diagnose or make treatment decisions."
)
