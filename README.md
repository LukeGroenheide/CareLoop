# CareLoop

> **CareLoop is the glue between doctor appointments.**

CareLoop is a bounded AI agent for **pre-visit clinical staff**. It tracks follow-up requests from the previous visit, interprets records that arrive afterward, and prepares an evidence-linked handoff before the patient returns.

This repository is a solo healthcare AI-agent hackathon project. It uses synthetic patient data and demonstrates a working longitudinal workflow rather than a production EHR integration.

## The problem

A clinician may request several follow-up actions at one appointment, but the supporting documentation arrives over the following days or months:

- laboratory results
- referral and scheduling records
- specialist notes
- medication records
- completed questionnaires
- patient-reported home monitoring

Before the return visit, staff still have to reconstruct what the clinician requested, which records arrived, what is documented as complete, what remains unresolved, and what needs human review.

CareLoop owns that between-visit interval. It evaluates documented follow-through against the prior plan instead of producing a generic chart summary.

## Demo scenario

The demo follows **Jordan Lee**, a synthetic 47-year-old patient preparing for a primary-care return visit.

At the previous visit, five follow-ups were requested:

1. Repeat HbA1c before the next visit.
2. Attend the ophthalmology consultation before the return visit.
3. Continue metformin 500 mg twice daily.
4. Complete a PHQ-9 questionnaire before the next visit.
5. Bring a seven-day home blood-pressure log to the next visit.

The baseline review produces:

| Follow-up | Finding |
| --- | --- |
| HbA1c | **Documented complete** |
| Ophthalmology | **Pending** |
| Metformin | **Documentation conflict** |
| PHQ-9 | **No record found** |
| Blood-pressure log | **Cannot verify** |

During the live workflow, CareLoop receives an ophthalmology consultation note, interprets it, assigns the deterministic source ID `OPH-NOTE-0911`, and adds it to the active session chart. The existing review remains visible but is marked as needing an update.

After the user updates the pre-visit review, the ophthalmology finding changes:

```text
Ophthalmology
Pending → Documented complete
New evidence: OPH-NOTE-0911
```

The new evidence and its original document remain inspectable.

## Agent architecture

CareLoop has two related workflows.

### Incoming record

```text
Raw synthetic document
        ↓
AI document interpretation through OpenClaw llm-task
        ↓
Deterministic Python validation
        ↓
Deterministic source ID + structured metadata
        ↓
Active Streamlit session chart
```

The interpretation call identifies the document category, document type, patient name, event date, and a concise factual summary. It does not assign a follow-up status or generate a task.

### Pre-visit review

```text
Previous-visit follow-up plan + available category names
        ↓
Agent selects relevant record categories for each plan item
        ↓
Python validates the requested categories
        ↓
Python retrieves only the allowed selected evidence
        ↓
Agent assesses each plan item against its evidence bundle
        ↓
Python validates plan coverage, statuses, and citations
        ↓
Evidence-linked pre-visit review
        ↓
Deterministic draft staff handoff
```

The model makes the semantic decisions; Python controls the state and the allowed operating boundary.

## Agent decisions and deterministic controls

### AI handles

- interpreting incoming clinical documents
- selecting relevant evidence categories for each prior-plan item
- assessing retrieved evidence and proposing structured findings

### Deterministic Python handles

- active session state and chart revisions
- allowed record categories
- evidence retrieval
- source ID assignment
- allowed status vocabulary
- citation and provenance validation
- rejecting duplicate, missing, or extra plan-item results
- ensuring every prior-plan item appears exactly once
- requiring cited evidence for `COMPLETED`
- draft staff-task generation
- before-and-after status comparison

No completion change is hardcoded into incoming-record ingestion. The later review reassesses the accumulated chart evidence.

## Evidence and provenance

Every positive finding links back to source records that staff can inspect. Python rejects nonexistent source IDs and citations outside the evidence selected for that plan item.

The medication finding demonstrates why inspection and human review matter:

```text
Prior plan
Metformin 500 mg twice daily

MED-LIST-0910 · Current medication list
Metformin 500 mg once daily

RX-FILL-0828 · Pharmacy fill history
Metformin 500 mg twice daily

CareLoop finding
Documentation conflict

Draft action
Flag inconsistent documented directions for clinician or pharmacist review
```

CareLoop does not decide which direction is correct, label the discrepancy as a medication error, or infer medication adherence.

Citation validation establishes reference integrity, not semantic truth. A model can still misinterpret a valid source, so CareLoop keeps findings reviewable and exposes the underlying evidence rather than claiming to eliminate hallucination.

## Longitudinal behavior

CareLoop tracks a chart revision and the revision assessed by the last successful review.

When a new record is successfully received:

- the chart revision advances
- the previous successful review remains visible
- the review is marked as stale
- the action changes to **Update pre-visit review**

After a successful update, CareLoop compares findings by stable plan-item ID and displays only changed statuses. Newly cited evidence is calculated deterministically by comparing the previous and current citation lists. If a status changes without a newly cited source, the UI states only that the assessment changed.

Failed ingestion does not advance the chart revision, and a failed review does not destroy the last valid review.

## Safety boundary

CareLoop verifies documented follow-through and prepares draft items for human review. It does not:

- diagnose
- prescribe
- change medications
- recommend treatment
- order tests
- autonomously contact patients
- determine which conflicting medication direction is correct
- treat missing documentation as proof that an action did not happen

> **Assessment is limited to the supplied records. Not documented does not mean not done.**

All patient data and clinical records in this repository are synthetic.

## Built with

- Python
- Streamlit
- OpenClaw
- OpenAI models through `llm-task`
- JSON
- Git and GitHub

No database, FHIR integration, external EHR, multi-agent framework, or real patient data is used.

## Run locally

The current project has been run with Python 3.12, Streamlit 1.63, and OpenClaw 2026.7.1-2.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install streamlit
python -m streamlit run app.py
```

A working OpenClaw installation and gateway with the `llm-task` tool configured for an OpenAI model are required for live ingestion and review calls.

The current implementation references the OpenClaw executable at:

```text
/home/luke/.openclaw/bin/openclaw
```

If OpenClaw is installed elsewhere, update the `OPENCLAW` constant near the top of `careloop_agent.py` before running the application. No environment-variable configuration is implemented in this version.

## Recorded demo sequence

```text
Previous-visit handoff
        ↓
Baseline pre-visit review
        ↓
Inspect conflicting metformin evidence
        ↓
Receive OPH-NOTE-0911
        ↓
Update the stale review
        ↓
Ophthalmology: Pending → Documented complete
        ↓
Review the updated draft staff handoff
```

The recording shows the agent operating on synthetic inputs, the evidence used for its findings, and the effect of a newly received record on a later review.

## Limitations

- The demo contains one synthetic patient workflow.
- State exists only in the active Streamlit session.
- There is no real EHR or external data integration.
- Care-plan amendments and supersession are not supported.
- Evidence selection operates at the record-category level.
- A model can still misinterpret a valid source.
- Citation checks do not guarantee that a source semantically supports a conclusion.
- The project does not perform autonomous clinical actions.
- It has not been clinically validated or evaluated for production deployment.
