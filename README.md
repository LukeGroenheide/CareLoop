# CareLoop

**CareLoop is the glue between doctor appointments.**

CareLoop is a bounded AI agent for pre-visit clinical staff. It tracks follow-up requests from a previous visit, interprets records that arrive afterward, and prepares an evidence-linked handoff before the patient returns.

## What it does

CareLoop:
- tracks requested follow-up from the previous visit
- interprets incoming synthetic clinical records
- decides which record categories matter for each follow-up item
- retrieves only the relevant evidence
- evaluates what is documented complete and what still needs review
- links findings back to source records
- prepares a bounded draft staff handoff
- updates findings when new evidence arrives

Example:

**Ophthalmology: Pending → Documented complete**

after a new consultation note is received and cited.

## How it works

Incoming record:

`Raw synthetic document → AI interpretation → Python validation → session chart`

Pre-visit review:

`Previous visit plan → agent selects relevant evidence categories → Python retrieves allowed records → agent assesses evidence → Python validates findings and citations → draft staff handoff`

## Agent vs deterministic controls

The AI agent handles:
- document interpretation
- evidence-category selection
- evidence assessment

Deterministic Python handles:
- state
- allowed categories
- source IDs
- evidence retrieval
- status validation
- citation validation
- staff-task generation

## Safety

CareLoop does not diagnose, prescribe, change medications, order tests, or autonomously contact patients.

Assessment is limited to the supplied records. **Not documented does not mean not done.**

All demo patient data is synthetic.

## Built with

- Python
- Streamlit
- OpenClaw
- OpenAI
- JSON

## Demo workflow

1. Review follow-up requests from the previous visit
2. Run the baseline pre-visit review
3. Inspect evidence behind unresolved findings
4. Receive a new ophthalmology consultation note
5. Update the review
6. See the finding change from **Pending** to **Documented complete**
7. Review the updated draft staff handoff

## Limitations

This hackathon prototype:
- uses synthetic data
- stores state only in the active Streamlit session
- does not connect to a real EHR
- does not support care-plan amendments
- does not guarantee that model interpretation of a valid source is correct

## Repository

Built for a healthcare AI agent hackathon.
