import json
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import streamlit as st

from careloop_agent import interpret_incoming_document, run_careloop


DATA_PATH = Path(__file__).parent / "data" / "demo_patient.json"

INCOMING_DOCUMENTS = {
    "Ophthalmology consultation note": {
        "source_prefix": "OPH-NOTE",
        "raw_document": """Document type: Ophthalmology Consultation Note
Patient: Jordan Lee
Date of service: 2026-09-11

Reason for visit:
Diabetic eye examination.

Encounter:
Patient was seen in ophthalmology clinic today. Dilated retinal examination was completed.

Follow-up:
Return according to ophthalmology follow-up schedule.""",
    },
    "Completed PHQ-9 questionnaire": {
        "source_prefix": "PHQ9",
        "raw_document": """Document type: PHQ-9 Questionnaire
Patient: Jordan Lee
Completed: 2026-09-12
Administration: Patient portal

All nine questionnaire items were answered.
Recorded item responses: 1, 1, 1, 0, 1, 1, 0, 1, 0
Recorded total score: 6

Submitted electronically on 2026-09-12.""",
    },
    "Seven-day home blood-pressure log": {
        "source_prefix": "BPLOG",
        "raw_document": """Document type: Seven-Day Home Blood Pressure Log
Patient: Jordan Lee
Source: Pre-visit intake
Submitted: 2026-09-14

2026-09-08 — 132/82 mmHg
2026-09-09 — 128/80 mmHg
2026-09-10 — 134/83 mmHg
2026-09-11 — 130/81 mmHg
2026-09-12 — 129/79 mmHg
2026-09-13 — 133/82 mmHg
2026-09-14 — 127/78 mmHg

Patient-entered home readings; one reading recorded each day.""",
    },
}

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


def build_active_chart(baseline_chart, received_records):
    active_chart = deepcopy(baseline_chart)
    for received in received_records:
        active_chart["records"][received["record_category"]].append(
            received["record"]
        )
    return active_chart


if "received_records" not in st.session_state:
    st.session_state.received_records = []

baseline_chart = load_demo_chart()
patient = baseline_chart["patient"]
plan_by_id = {
    item["id"]: item["text"]
    for item in baseline_chart["previous_visit"]["plan_items"]
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

st.divider()
timeline_columns = st.columns(3)
with timeline_columns[0]:
    st.markdown("**1 · Previous Visit**")
    st.write(
        datetime.fromisoformat(
            baseline_chart["previous_visit"]["date"]
        ).strftime("%b %d, %Y")
    )
    st.caption(f"{len(plan_by_id)} follow-up items documented")
with timeline_columns[1]:
    st.markdown("**2 · Incoming Records**")
    st.write(f"{len(st.session_state.received_records)} received this session")
    st.caption("Documentation accumulates between visits")
with timeline_columns[2]:
    st.markdown("**3 · Upcoming Visit**")
    st.write(format_visit(patient["upcoming_visit"]))
    st.caption("Run the pre-visit review")

st.subheader("Incoming Records")
selected_document_name = st.selectbox(
    "Select a synthetic document",
    options=list(INCOMING_DOCUMENTS),
    key="incoming_document_preset",
)
selected_document = INCOMING_DOCUMENTS[selected_document_name]

with st.expander("Preview synthetic document", expanded=True):
    st.code(selected_document["raw_document"], language=None)

already_received = any(
    received["preset_name"] == selected_document_name
    for received in st.session_state.received_records
)
action_columns = st.columns([1, 1, 3])
receive_clicked = action_columns[0].button(
    "Receive Record",
    type="primary",
    use_container_width=True,
    disabled=already_received,
)
reset_clicked = action_columns[1].button(
    "Reset Demo",
    use_container_width=True,
)

if reset_clicked:
    st.session_state.received_records = []
    st.session_state.pop("careloop_results", None)
    st.session_state.pop("last_received_message", None)
    st.session_state.pop("incoming_document_preset", None)
    st.rerun()

if receive_clicked:
    try:
        started_at = time.perf_counter()
        with st.spinner("Interpreting incoming record…"):
            received = interpret_incoming_document(
                baseline_chart,
                selected_document["raw_document"],
                selected_document["source_prefix"],
            )
        received["preset_name"] = selected_document_name
        received["ingestion_seconds"] = time.perf_counter() - started_at
        st.session_state.received_records = [
            *st.session_state.received_records,
            received,
        ]
        st.session_state.pop("careloop_results", None)
        st.session_state.last_received_message = (
            f"Received {received['source_id']} and added it to the "
            "session chart."
        )
        st.rerun()
    except Exception as exc:
        st.error(f"CareLoop could not interpret the record: {exc}")

if "last_received_message" in st.session_state:
    st.success(st.session_state.pop("last_received_message"))

if st.session_state.received_records:
    st.markdown("**Received this session**")
    for received in st.session_state.received_records:
        interpretation = received["interpretation"]
        with st.expander(
            f"✓ {received['source_id']} — {interpretation['document_type']}"
        ):
            st.caption(
                f"{received['record_category'].replace('_', ' ').title()} "
                f"· Event date {interpretation['event_date']} "
                f"· Interpreted in {received['ingestion_seconds']:.1f}s"
            )
            st.write(interpretation["summary"])
            st.code(received["raw_document"], language=None)
else:
    st.caption("No additional records received in this session.")

active_chart = build_active_chart(
    baseline_chart, st.session_state.received_records
)

st.divider()
st.subheader("Upcoming Visit · Pre-Visit Review")
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
            st.session_state.careloop_results = run_careloop(chart=active_chart)
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
                            if key == "raw_document":
                                st.markdown("**Original document**")
                                st.code(value, language=None)
                            elif key != "source_id":
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
