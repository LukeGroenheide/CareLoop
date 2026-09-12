import json
import time
from copy import deepcopy
from datetime import datetime
from html import escape
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

STATUS_LABELS = {
    "COMPLETED": "Documented complete",
    "PENDING": "Pending",
    "NOT FOUND": "No record found",
    "CONFLICTING": "Documentation conflict",
    "CANNOT VERIFY": "Cannot verify",
}

PLAN_LABELS = {
    "a1c": "HbA1c",
    "eye_referral": "Ophthalmology",
    "metformin": "Metformin",
    "phq9": "PHQ-9",
    "bp_log": "Home blood-pressure log",
}

SESSION_DEFAULTS = {
    "received_records": [],
    "chart_revision": 0,
    "reviewed_revision": None,
    "careloop_results": None,
    "previous_careloop_results": None,
    "latest_status_changes": [],
    "last_received_record": None,
    "last_review_seconds": None,
}

st.set_page_config(
    page_title="CareLoop",
    page_icon="✓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        :root { color-scheme: light; }
        .stApp { background: #f5f7f6; color: #1f2937; }
        .block-container { max-width: 1320px; padding-top: 1.35rem; padding-bottom: 2.5rem; }
        h1, h2, h3 { color: #17262a; letter-spacing: -0.02em; }
        h1 { font-size: 2rem !important; margin-bottom: 0 !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1rem !important; }
        p, li { line-height: 1.45; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff; border-color: #dde5e2 !important; border-radius: 0.6rem;
        }
        [data-testid="stMetric"] {
            background: #ffffff; border: 1px solid #dde5e2; border-radius: 0.5rem;
            padding: 0.55rem 0.7rem;
        }
        [data-testid="stMetricLabel"] { font-size: 0.72rem; color: #66757a; }
        [data-testid="stMetricValue"] { font-size: 1.35rem; color: #17262a; }
        div.stButton > button { min-height: 2.55rem; border-radius: 0.45rem; font-weight: 650; }
        div.stButton > button[kind="primary"] { background: #0f766e; border-color: #0f766e; }
        div[data-testid="stExpander"] {
            background: #ffffff; border-color: #dde5e2; border-radius: 0.5rem;
        }
        .product-title { display: flex; align-items: baseline; gap: 0.8rem; }
        .product-title strong { color: #0f766e; font-size: 2rem; letter-spacing: -0.04em; }
        .product-title span { color: #53646a; font-size: 1rem; }
        .patient-line { color: #43555b; margin: 0.1rem 0 1rem; }
        .synthetic-tag {
            color: #0f766e; background: #e9f4f1; border: 1px solid #cfe5df;
            border-radius: 0.3rem; font-size: 0.75rem; padding: 0.12rem 0.38rem; margin-left: 0.35rem;
        }
        .lifecycle {
            display: grid; grid-template-columns: minmax(120px, .8fr) minmax(220px, 2.7fr) minmax(120px, .8fr);
            align-items: center; background: #ffffff; border: 1px solid #dde5e2;
            border-radius: 0.6rem; padding: 0.7rem 1rem; margin-bottom: 0.8rem;
        }
        .lifecycle-end { color: #17262a; }
        .lifecycle-end.right { text-align: right; }
        .lifecycle-date { color: #0f766e; font-size: 0.72rem; font-weight: 750; letter-spacing: 0.08em; }
        .lifecycle-label { font-size: 0.9rem; font-weight: 650; }
        .lifecycle-middle { display: flex; align-items: center; color: #66757a; font-size: 0.78rem; }
        .lifecycle-middle::before, .lifecycle-middle::after {
            content: ""; height: 1px; background: #bccbc7; flex: 1; margin: 0 0.65rem;
        }
        .handoff {
            background: #ffffff; border: 1px solid #dde5e2; border-left: 3px solid #0f766e;
            border-radius: 0.55rem; padding: 0.7rem 0.9rem; margin-bottom: 1.1rem;
        }
        .eyebrow { color: #66757a; font-size: 0.69rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
        .handoff-title { color: #17262a; font-weight: 700; margin: 0.1rem 0; }
        .handoff-list {
            display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .18rem 1.4rem;
            margin: 0; padding-left: 1.25rem;
        }
        .handoff-list li { color: #304248; font-size: 0.82rem; padding-right: 0.4rem; }
        .section-heading { color: #17262a; font-size: 1.05rem; font-weight: 750; margin-bottom: .08rem; }
        .section-kicker { color: #66757a; font-size: .78rem; margin-bottom: .55rem; }
        .feed-row { display: grid; grid-template-columns: 3.5rem .7rem 1fr; gap: .35rem; min-height: 3.05rem; }
        .feed-date { color: #596a70; font-size: .72rem; padding-top: .1rem; }
        .feed-rail { position: relative; }
        .feed-dot {
            position: absolute; left: .19rem; top: .28rem; width: .45rem; height: .45rem;
            border-radius: 50%; background: #8da5a0;
        }
        .feed-dot.session { background: #0f766e; box-shadow: 0 0 0 3px #dceeea; }
        .feed-line { position: absolute; left: .39rem; top: .82rem; bottom: -.1rem; width: 1px; background: #d7e0dd; }
        .feed-title { color: #26383e; font-size: .82rem; font-weight: 680; }
        .feed-summary { color: #66757a; font-size: .73rem; line-height: 1.3; }
        .feed-origin { color: #7a898e; font-size: .66rem; text-transform: uppercase; letter-spacing: .04em; }
        .feed-origin.session { color: #0f766e; font-weight: 700; }
        .ingest-confirm {
            background: #eef7f4; border: 1px solid #cfe5df; border-radius: .5rem;
            padding: .65rem .75rem; margin: .6rem 0;
        }
        .ingest-id { color: #0f766e; font-weight: 750; font-size: .83rem; }
        .ingest-meta { color: #53646a; font-size: .75rem; }
        .stale-note {
            background: #eef4f6; border-left: 3px solid #52788a; color: #35515e;
            border-radius: .35rem; padding: .55rem .7rem; margin: .35rem 0 .65rem; font-size: .82rem;
        }
        .delta-panel {
            background: #eef7f4; border: 1px solid #cfe5df; border-radius: .5rem;
            padding: .65rem .75rem; margin: .4rem 0 .8rem;
        }
        .delta-item { display: grid; grid-template-columns: 1fr auto; gap: .5rem; align-items: center; margin-top: .25rem; }
        .delta-name { color: #23363b; font-size: .83rem; font-weight: 700; }
        .delta-change { color: #0f766e; font-size: .78rem; font-weight: 700; }
        .delta-source { color: #66757a; font-size: .72rem; grid-column: 1 / -1; }
        .status-badge {
            display: inline-block; border-radius: .3rem; padding: .12rem .38rem;
            font-size: .68rem; font-weight: 750; letter-spacing: .025em;
        }
        .status-completed { color: #0b685f; background: #e4f2ee; }
        .status-pending { color: #315d73; background: #e8f0f4; }
        .status-not-found { color: #5f6a6e; background: #edf0f1; }
        .status-conflicting { color: #865b16; background: #f8edd8; }
        .status-cannot-verify { color: #4c5966; background: #e9edf1; }
        .finding-title { color: #21343a; font-weight: 700; font-size: .88rem; margin: .15rem 0; }
        .finding-summary { color: #485a60; font-size: .8rem; line-height: 1.4; margin-bottom: .2rem; }
        .finding-meta { color: #7a898e; font-size: .69rem; }
        .comparison-label { color: #66757a; font-size: .68rem; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
        .comparison-value { color: #17262a; font-size: 1rem; font-weight: 750; margin: .15rem 0; }
        .conflict-callout { border-left: 3px solid #b47a24; padding-left: .7rem; color: #394b51; margin: .6rem 0; }
        .task-row { padding: .45rem 0; border-top: 1px solid #e6ecea; }
        .task-action { color: #26383e; font-size: .82rem; font-weight: 700; }
        .task-meta, .quiet-safety { color: #66757a; font-size: .72rem; }
        .quiet-safety { line-height: 1.45; }
        @media (max-width: 850px) {
            .handoff-list { grid-template-columns: 1fr; }
            .lifecycle { grid-template-columns: 1fr; gap: .3rem; }
            .lifecycle-middle { justify-content: center; }
            .lifecycle-end.right { text-align: left; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_demo_chart():
    return json.loads(DATA_PATH.read_text())


def format_date(value, pattern="%b %d"):
    try:
        return datetime.fromisoformat(value).strftime(pattern).replace(" 0", " ")
    except (TypeError, ValueError):
        return value


def build_active_chart(baseline_chart, received_records):
    active_chart = deepcopy(baseline_chart)
    for received in received_records:
        active_chart["records"][received["record_category"]].append(received["record"])
    return active_chart


def compare_reviews(previous_review, current_review):
    previous_by_id = {item["item_id"]: item for item in previous_review["results"]}
    changes = []
    for current in current_review["results"]:
        previous = previous_by_id.get(current["item_id"])
        if previous is None or previous["status"] == current["status"]:
            continue
        previous_sources = set(previous.get("source_ids", []))
        newly_cited = [
            source_id
            for source_id in current.get("source_ids", [])
            if source_id not in previous_sources
        ]
        changes.append(
            {
                "item_id": current["item_id"],
                "previous_status": previous["status"],
                "current_status": current["status"],
                "new_source_ids": newly_cited,
            }
        )
    return changes


def record_event_date(record):
    for key in ("event_date", "collected_date", "updated", "filled", "date", "ordered"):
        if record.get(key):
            return record[key]
    return ""


def describe_baseline_record(category, record):
    if category == "labs":
        return record.get("test", "Laboratory result"), f"Final result · {record.get('result', '')}"
    if category == "referrals":
        return (
            f"{record.get('specialty', 'Specialty')} referral",
            f"Scheduled {format_date(record.get('appointment_date'))} · after return visit",
        )
    if category == "medications":
        return (
            record.get("source", "Medication record").title(),
            f"{record.get('name', '')} {record.get('dose', '')} · {record.get('frequency', '')}",
        )
    if category == "intake":
        return "Pre-visit intake", record.get("text", "")
    if category == "questionnaires":
        return "Questionnaire", record.get("summary", "")
    if category == "specialist_notes":
        return record.get("document_type", "Specialist note"), record.get("summary", "")
    return category.replace("_", " ").title(), record.get("summary", "")


def build_activity_feed(baseline_chart, received_records):
    activity = []
    for category, records in baseline_chart["records"].items():
        for record in records:
            title, summary = describe_baseline_record(category, record)
            activity.append(
                {
                    "date": record_event_date(record),
                    "title": title,
                    "summary": summary,
                    "source_id": record.get("source_id", ""),
                    "origin": "Supplied chart",
                    "session": False,
                }
            )
    for received in received_records:
        interpretation = received["interpretation"]
        activity.append(
            {
                "date": interpretation["event_date"],
                "title": interpretation["document_type"],
                "summary": interpretation["summary"],
                "source_id": received["source_id"],
                "origin": "Added this session",
                "session": True,
            }
        )
    return sorted(activity, key=lambda item: (item["date"], item["source_id"]))


def status_badge(status):
    css_class = status.lower().replace(" ", "-")
    return (
        f'<span class="status-badge status-{css_class}">'
        f"{escape(STATUS_LABELS[status])}</span>"
    )


def render_source_record(source_id, source):
    record = source["record"]
    st.markdown(f"**{source_id}**")
    st.caption(source["record_category"].replace("_", " ").title())
    for key, value in record.items():
        if key in {"source_id", "raw_document"}:
            continue
        st.markdown(f"- **{key.replace('_', ' ').title()}:** {value}")
    if record.get("raw_document"):
        st.markdown("**Original document**")
        st.code(record["raw_document"], language=None)


def render_medication_comparison(source_records, plan_text, task):
    with st.expander("Compare 2 sources", expanded=False):
        st.markdown('<div class="comparison-label">Prior plan</div>', unsafe_allow_html=True)
        st.markdown(f"**{plan_text}**")
        columns = st.columns(2)
        for column, source_id in zip(columns, ("MED-LIST-0910", "RX-FILL-0828")):
            with column:
                source = source_records.get(source_id)
                if source is None:
                    st.caption(f"{source_id} was not in the retrieved evidence.")
                    continue
                record = source["record"]
                record_date = record.get("updated") or record.get("filled") or ""
                st.markdown(
                    f'<div class="comparison-label">{escape(source_id)}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{record.get('source', 'Medication record').title()}**")
                st.caption(format_date(record_date))
                st.markdown(
                    f'<div class="comparison-value">{escape(record.get("dose", ""))}<br>'
                    f'{escape(record.get("frequency", "").upper())}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**Complete source record**")
                st.markdown(
                    f"Name: {record.get('name', '')}  \n"
                    f"Dose: {record.get('dose', '')}  \n"
                    f"Frequency: {record.get('frequency', '')}"
                )
        st.markdown(
            '<div class="conflict-callout"><strong>Documentation conflict</strong><br>'
            "The supplied records contain different documented directions.</div>",
            unsafe_allow_html=True,
        )
        if task:
            st.caption("DRAFT STAFF ACTION")
            st.write(task["task"] + ".")


def render_finding(item, source_records, plan_by_id, task_by_item, compact=False):
    item_id = item["item_id"]
    plan_text = plan_by_id.get(item_id, item_id)
    st.markdown(status_badge(item["status"]), unsafe_allow_html=True)
    st.markdown(f'<div class="finding-title">{escape(plan_text)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="finding-summary">{escape(item["evidence_summary"])}</div>',
        unsafe_allow_html=True,
    )
    categories = ", ".join(
        category.replace("_", " ") for category in item["record_categories_checked"]
    )
    st.markdown(
        f'<div class="finding-meta">Evidence checked: {escape(categories)}</div>',
        unsafe_allow_html=True,
    )

    if compact:
        source_ids = item.get("source_ids", [])
        for source_id in source_ids:
            source = source_records.get(source_id)
            if not source:
                continue
            st.markdown(f"**Source evidence · {source_id}**")
            record = source["record"]
            for key, value in record.items():
                if key in {"source_id", "raw_document"}:
                    continue
                st.markdown(f"- **{key.replace('_', ' ').title()}:** {value}")
            if record.get("raw_document"):
                st.markdown("**Original document**")
                st.code(record["raw_document"], language=None)
        return
    if item_id == "metformin":
        render_medication_comparison(source_records, plan_text, task_by_item.get(item_id))
        return

    source_ids = item.get("source_ids", [])
    label = f"View source evidence · {len(source_ids)}" if source_ids else "View evidence checked"
    with st.expander(label, expanded=False):
        if not source_ids:
            st.caption("No positive source record documents completion in the supplied evidence.")
        for index, source_id in enumerate(source_ids):
            source = source_records.get(source_id)
            if source:
                if index:
                    st.divider()
                render_source_record(source_id, source)


def render_task_evidence(item, source_records):
    source_ids = item.get("source_ids", [])
    if not source_ids:
        return
    with st.expander(f"Task evidence · {len(source_ids)} source(s)", expanded=False):
        for index, source_id in enumerate(source_ids):
            source = source_records.get(source_id)
            if source:
                if index:
                    st.divider()
                render_source_record(source_id, source)


for key, default in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = deepcopy(default)

baseline_chart = load_demo_chart()
patient = baseline_chart["patient"]
plan_items = baseline_chart["previous_visit"]["plan_items"]
plan_by_id = {item["id"]: item["text"] for item in plan_items}
plan_order = {item["id"]: index for index, item in enumerate(plan_items)}
active_chart = build_active_chart(baseline_chart, st.session_state.received_records)

previous_date = format_date(baseline_chart["previous_visit"]["date"])
upcoming_date = format_date(patient["upcoming_visit"])
handoff_items_html = "".join(f"<li>{escape(item['text'])}</li>" for item in plan_items)

st.markdown(
    f"""
    <div class="product-title"><strong>CareLoop</strong><span>The glue between appointments.</span></div>
    <div class="patient-line">
        {escape(patient['name'])} · {patient['age']} · Primary-care return
        <span class="synthetic-tag">Synthetic demo</span>
    </div>
    <div class="lifecycle">
        <div class="lifecycle-end">
            <div class="lifecycle-date">{escape(previous_date.upper())}</div>
            <div class="lifecycle-label">Previous visit</div>
        </div>
        <div class="lifecycle-middle">Records between visits</div>
        <div class="lifecycle-end right">
            <div class="lifecycle-date">{escape(upcoming_date.upper())}</div>
            <div class="lifecycle-label">Return visit</div>
        </div>
    </div>
    <div class="handoff">
        <div class="eyebrow">Previous visit handoff · {escape(previous_date)}</div>
        <div class="handoff-title">Five requested follow-ups</div>
        <ol class="handoff-list">{handoff_items_html}</ol>
    </div>
    """,
    unsafe_allow_html=True,
)

left_column, right_column = st.columns([0.38, 0.62], gap="large")

with left_column:
    st.markdown('<div class="section-heading">Between-visit records</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-kicker">Event dates from the supplied chart and this session</div>',
        unsafe_allow_html=True,
    )
    activity = build_activity_feed(baseline_chart, st.session_state.received_records)
    activity_html = []
    for index, event in enumerate(activity):
        session_class = " session" if event["session"] else ""
        rail = "" if index == len(activity) - 1 else '<span class="feed-line"></span>'
        activity_html.append(
            f"""
            <div class="feed-row">
                <div class="feed-date">{escape(format_date(event['date']))}</div>
                <div class="feed-rail"><span class="feed-dot{session_class}"></span>{rail}</div>
                <div>
                    <div class="feed-title">{escape(event['title'])}</div>
                    <div class="feed-summary">{escape(event['summary'])}</div>
                    <div class="feed-origin{session_class}">{escape(event['origin'])} · {escape(event['source_id'])}</div>
                </div>
            </div>
            """
        )
    st.markdown("".join(activity_html), unsafe_allow_html=True)

    st.markdown("#### Incoming record")
    selected_document_name = st.selectbox(
        "Synthetic source document",
        options=list(INCOMING_DOCUMENTS),
        key="incoming_document_preset",
    )
    selected_document = INCOMING_DOCUMENTS[selected_document_name]
    with st.expander("Preview document", expanded=False):
        st.code(selected_document["raw_document"], language=None)

    already_received = any(
        received["preset_name"] == selected_document_name
        for received in st.session_state.received_records
    )
    receive_clicked = st.button(
        "Receive record",
        key="receive_record",
        type="primary",
        use_container_width=True,
        disabled=already_received,
    )
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
            st.session_state.received_records = [*st.session_state.received_records, received]
            st.session_state.chart_revision += 1
            st.session_state.last_received_record = received
            st.session_state.latest_status_changes = []
            st.rerun()
        except Exception as exc:
            st.error(f"CareLoop could not interpret the record: {exc}")

    last_received = st.session_state.last_received_record
    if last_received:
        interpretation = last_received["interpretation"]
        st.markdown(
            f"""
            <div class="ingest-confirm">
                <div class="eyebrow">Added to session chart</div>
                <div class="ingest-id">{escape(last_received['source_id'])}</div>
                <div class="finding-title">{escape(interpretation['document_type'])}</div>
                <div class="ingest-meta">
                    {escape(last_received['record_category'].replace('_', ' ').title())}
                    · {escape(format_date(interpretation['event_date']))}
                    · interpreted in {last_received['ingestion_seconds']:.1f}s
                </div>
                <div class="finding-summary">{escape(interpretation['summary'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("View original received document", expanded=False):
            st.code(last_received["raw_document"], language=None)

with right_column:
    st.markdown('<div class="section-heading">Pre-visit review</div>', unsafe_allow_html=True)
    current_review = st.session_state.careloop_results
    reviewed_revision = st.session_state.reviewed_revision
    review_is_stale = (
        current_review is not None
        and reviewed_revision is not None
        and st.session_state.chart_revision > reviewed_revision
    )
    review_label = "Update pre-visit review" if review_is_stale else "Run pre-visit review"
    review_disabled = current_review is not None and not review_is_stale
    run_clicked = st.button(
        review_label,
        key="run_review",
        type="primary",
        use_container_width=False,
        disabled=review_disabled,
    )
    if review_is_stale:
        st.markdown(
            '<div class="stale-note"><strong>New record received</strong> · '
            "Pre-visit review needs updating</div>",
            unsafe_allow_html=True,
        )

    if run_clicked:
        review_status = st.status("Selecting relevant evidence…", expanded=True)

        def update_review_stage(stage):
            if stage == "reviewing":
                review_status.update(label="Reviewing retrieved records…")

        try:
            started_at = time.perf_counter()
            new_review = run_careloop(chart=active_chart, progress_callback=update_review_stage)
            elapsed = time.perf_counter() - started_at
            previous_review = st.session_state.careloop_results
            changes = compare_reviews(previous_review, new_review) if previous_review else []
            st.session_state.previous_careloop_results = previous_review
            st.session_state.careloop_results = new_review
            st.session_state.reviewed_revision = st.session_state.chart_revision
            st.session_state.latest_status_changes = changes
            st.session_state.last_review_seconds = elapsed
            current_review = new_review
            reviewed_revision = st.session_state.reviewed_revision
            review_is_stale = False
            review_status.update(
                label=f"Review complete in {elapsed:.1f}s", state="complete", expanded=False
            )
        except Exception as exc:
            review_status.update(label="Review failed", state="error", expanded=False)
            st.error(f"CareLoop could not complete the review: {exc}")

    if current_review is None:
        st.caption(
            "Assess each prior-plan item against the records documented before the return visit."
        )
    else:
        results = current_review["results"]
        tasks = current_review["staff_tasks"]
        source_records = current_review["source_records"]
        result_by_id = {item["item_id"]: item for item in results}
        task_by_item = {task["item_id"]: task for task in tasks}
        completed_items = [item for item in results if item["status"] == "COMPLETED"]
        unresolved_items = [item for item in results if item["status"] != "COMPLETED"]
        unresolved_items.sort(
            key=lambda item: (
                0 if item["item_id"] == "metformin" else 1,
                plan_order.get(item["item_id"], 999),
            )
        )
        completed_items.sort(key=lambda item: plan_order.get(item["item_id"], 999))

        metric_columns = st.columns(4)
        metric_columns[0].metric("Plan items", len(results))
        metric_columns[1].metric("Complete", len(completed_items))
        metric_columns[2].metric("Needs review", len(unresolved_items))
        metric_columns[3].metric("Draft actions", len(tasks))
        if st.session_state.last_review_seconds is not None:
            revision_note = f"Chart revision {reviewed_revision}"
            if review_is_stale:
                revision_note += (
                    " · viewing last valid review while chart is at revision "
                    f"{st.session_state.chart_revision}"
                )
            else:
                revision_note += f" · reviewed in {st.session_state.last_review_seconds:.1f}s"
            st.caption(revision_note)

        changes = st.session_state.latest_status_changes
        if changes and not review_is_stale:
            change_rows = []
            for change in sorted(changes, key=lambda item: plan_order.get(item["item_id"], 999)):
                source_text = (
                    "New evidence: " + " · ".join(change["new_source_ids"])
                    if change["new_source_ids"]
                    else "Assessment changed"
                )
                change_rows.append(
                    f"""
                    <div class="delta-item">
                        <div class="delta-name">{escape(PLAN_LABELS.get(change['item_id'], change['item_id']))}</div>
                        <div class="delta-change">
                            {escape(STATUS_LABELS[change['previous_status']])} → {escape(STATUS_LABELS[change['current_status']])}
                        </div>
                        <div class="delta-source">{escape(source_text)}</div>
                    </div>
                    """
                )
            st.markdown(
                '<div class="delta-panel"><div class="eyebrow">Changed since last review</div>'
                + "".join(change_rows)
                + "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("#### Needs review")
        for item in unresolved_items:
            with st.container(border=True):
                render_finding(item, source_records, plan_by_id, task_by_item)

        with st.expander(f"Documented complete · {len(completed_items)}", expanded=False):
            for index, item in enumerate(completed_items):
                if index:
                    st.divider()
                render_finding(item, source_records, plan_by_id, task_by_item, compact=True)

        st.markdown("#### Draft staff handoff")
        st.caption("Prepared for review · Not sent or assigned")
        if not tasks:
            st.caption("No draft staff actions were created.")
        else:
            for task in tasks:
                finding = result_by_id[task["item_id"]]
                st.markdown(
                    f"""
                    <div class="task-row">
                        <div class="task-action">{escape(task['task'])}</div>
                        <div class="task-meta">
                            {escape(plan_by_id[task['item_id']])}<br>
                            {escape(STATUS_LABELS[task['status']])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                render_task_evidence(finding, source_records)

st.divider()
footer_columns = st.columns([5, 1])
with footer_columns[0]:
    st.markdown(
        '<div class="quiet-safety">Assessment is limited to the supplied records. '
        "Not documented does not mean not done.<br>CareLoop verifies documented "
        "follow-through. It does not diagnose or make treatment decisions.</div>",
        unsafe_allow_html=True,
    )
with footer_columns[1]:
    reset_clicked = st.button("Reset demo", key="reset_demo", use_container_width=True)

if reset_clicked:
    for key in SESSION_DEFAULTS:
        st.session_state.pop(key, None)
    st.session_state.pop("incoming_document_preset", None)
    st.rerun()
