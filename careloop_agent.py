import json
import subprocess
from datetime import date
from pathlib import Path

OPENCLAW = "/home/luke/.openclaw/bin/openclaw"

ALLOWED_STATUSES = {
    "COMPLETED",
    "PENDING",
    "NOT FOUND",
    "CONFLICTING",
    "CANNOT VERIFY",
}


def load_chart(path="data/demo_patient.json"):
    return json.loads(Path(path).read_text())


def build_evidence_selection_schema(record_categories):
    return {
        "type": "object",
        "properties": {
            "requests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "record_categories": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": sorted(record_categories),
                            },
                        },
                    },
                    "required": ["item_id", "record_categories"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requests"],
        "additionalProperties": False,
    }


def build_assessment_schema():
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": sorted(ALLOWED_STATUSES),
                        },
                        "evidence_summary": {"type": "string"},
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "item_id",
                        "status",
                        "evidence_summary",
                        "source_ids",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def build_incoming_document_schema(record_categories):
    return {
        "type": "object",
        "properties": {
            "record_category": {
                "type": "string",
                "enum": sorted(record_categories),
            },
            "document_type": {"type": "string"},
            "patient_name": {"type": "string"},
            "event_date": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": [
            "record_category",
            "document_type",
            "patient_name",
            "event_date",
            "summary",
        ],
        "additionalProperties": False,
    }


def call_llm_task(prompt, schema):
    params = {
        "name": "llm-task",
        "args": {
            "prompt": prompt,
            "thinking": "low",
            "schema": schema,
        },
    }

    result = subprocess.run(
        [
            OPENCLAW,
            "gateway",
            "call",
            "tools.invoke",
            "--json",
            "--timeout",
            "60000",
            "--params",
            json.dumps(params),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    response = json.loads(result.stdout)

    if not response.get("ok"):
        raise RuntimeError(response)

    return response["output"]["details"]["json"]


def validate_incoming_document(chart, interpretation):
    required_fields = {
        "record_category",
        "document_type",
        "patient_name",
        "event_date",
        "summary",
    }
    if set(interpretation) != required_fields:
        raise ValueError("Incoming-document interpretation has invalid fields.")

    for field in required_fields:
        if not isinstance(interpretation[field], str) or not interpretation[
            field
        ].strip():
            raise ValueError(f"Incoming-document field {field} is required.")

    if interpretation["record_category"] not in chart.get("records", {}):
        raise ValueError(
            "Incoming document used an invalid record category: "
            f"{interpretation['record_category']}"
        )

    if interpretation["patient_name"] != chart["patient"]["name"]:
        raise ValueError(
            "Incoming document patient does not match the synthetic patient."
        )

    try:
        date.fromisoformat(interpretation["event_date"])
    except ValueError as exc:
        raise ValueError(
            "Incoming-document event_date must use YYYY-MM-DD."
        ) from exc

    return interpretation


def interpret_incoming_document(chart, raw_document, source_prefix):
    record_categories = list(chart.get("records", {}).keys())
    prompt = f"""
You interpret one synthetic clinical document for storage in a chart.

Describe only what the supplied document states. Identify its best matching
record category, document type, patient name, event date, and a concise factual
summary. For a document covering multiple dates, use its completion or latest
recorded date as event_date.

Do not compare this document with a care plan. Do not assign a completion
status, generate tasks, diagnose, recommend treatment, decide medication
changes, or invent facts.

Return ONE JSON object with exactly this structure:
{{
  "record_category": "...",
  "document_type": "...",
  "patient_name": "...",
  "event_date": "YYYY-MM-DD",
  "summary": "..."
}}

record_category must be one of the available category names. Do not generate a
source ID. Do not wrap the JSON in markdown or code fences.

Category guidance:
- labs: laboratory test records
- referrals: referral orders, scheduling, or referral status records
- medications: medication lists or dispensing records
- questionnaires: standardized questionnaires such as PHQ-9
- intake: patient-supplied pre-visit information and home-monitoring logs
- specialist_notes: documentation of completed specialist encounters

AVAILABLE RECORD CATEGORIES:
{json.dumps(record_categories, indent=2)}

RAW SYNTHETIC DOCUMENT:
{raw_document}
"""

    interpretation = call_llm_task(
        prompt, build_incoming_document_schema(record_categories)
    )
    validated = validate_incoming_document(chart, interpretation)
    event_date = date.fromisoformat(validated["event_date"])
    source_id = f"{source_prefix}-{event_date.strftime('%m%d')}"

    return {
        "source_id": source_id,
        "record_category": validated["record_category"],
        "raw_document": raw_document,
        "interpretation": validated,
        "record": {
            "source_id": source_id,
            "document_type": validated["document_type"],
            "patient_name": validated["patient_name"],
            "event_date": validated["event_date"],
            "summary": validated["summary"],
            "raw_document": raw_document,
        },
    }


def select_evidence(chart):
    plan_items = chart["previous_visit"]["plan_items"]
    record_categories = list(chart.get("records", {}).keys())

    prompt = f"""
You are selecting chart evidence for a pre-visit care-plan review.

For each prior plan item, choose the smallest set of available record
categories that is plausibly relevant to determining whether the requested
follow-up is documented. Select categories even when they may contain no
records, because an empty relevant category can support a NOT FOUND result.
Choose enough categories to distinguish completion from scheduling or other
progress; do not inspect only the category where final completion would appear.
For example, assessing attendance at a consultation may require referral
records for scheduling and specialist notes for completion.

Return exactly one request for every plan item. Use only the supplied item IDs
and category names. Do not invent tools, categories, or records.

Return ONE JSON object with exactly this top-level structure:
{{
  "requests": [
    {{
      "item_id": "...",
      "record_categories": ["..."]
    }}
  ]
}}

The object must have exactly one top-level key: "requests".
Each request must have exactly the keys "item_id" and "record_categories".
Do NOT use a key named "categories".
Do NOT return a bare array.
Do NOT wrap the JSON in markdown or code fences.

PRIOR PLAN ITEMS:
{json.dumps(plan_items, indent=2)}

AVAILABLE RECORD CATEGORIES:
{json.dumps(record_categories, indent=2)}
"""

    selection = call_llm_task(
        prompt, build_evidence_selection_schema(record_categories)
    )
    return validate_evidence_selection(chart, selection)


def validate_evidence_selection(chart, selection):
    expected_ids = {
        item["id"] for item in chart["previous_visit"]["plan_items"]
    }
    available_categories = set(chart.get("records", {}).keys())
    requests = selection["requests"]
    actual_ids = [request["item_id"] for request in requests]

    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("Agent returned duplicate evidence requests.")

    if set(actual_ids) != expected_ids:
        raise ValueError(
            "Evidence-request mismatch. "
            f"Expected {expected_ids}, got {set(actual_ids)}"
        )

    for request in requests:
        categories = request["record_categories"]
        if not categories:
            raise ValueError(
                f"No evidence categories requested for {request['item_id']}."
            )
        if len(categories) != len(set(categories)):
            raise ValueError(
                f"Duplicate evidence categories for {request['item_id']}."
            )
        invalid_categories = set(categories) - available_categories
        if invalid_categories:
            raise ValueError(
                f"Agent requested invalid record categories: {invalid_categories}"
            )

    return selection


def retrieve_evidence(chart, selection):
    return {
        request["item_id"]: {
            "record_categories": request["record_categories"],
            "records": {
                category: chart["records"][category]
                for category in request["record_categories"]
            },
        }
        for request in selection["requests"]
    }


def call_agent(chart, evidence_by_item):
    review_context = {
        "patient": {
            "upcoming_visit": chart["patient"]["upcoming_visit"],
        },
        "previous_visit": chart["previous_visit"],
        "evidence_by_item": evidence_by_item,
    }
    prompt = f"""
You are CareLoop, a pre-visit care-plan verification agent.

Your job is NOT to summarize the chart generally.
For every prior plan item, determine whether what was supposed to happen
actually happened before the upcoming visit.

Use only the synthetic evidence retrieved for each plan item. Assess every
item only from the records in that item's evidence bundle. A source ID from
another item's bundle is not available evidence for this item.

Status meanings:
COMPLETED = clear evidence the requested action occurred.
PENDING = action exists/in progress but is not complete.
NOT FOUND = expected evidence is absent from the supplied records.
CONFLICTING = supplied records disagree in a way relevant to the plan.
CANNOT VERIFY = evidence suggests something may have happened, but the
requested action cannot actually be verified.

Describe what is documented, not what the patient definitely did. Do not
diagnose, recommend treatment, change medications, infer nonadherence, decide
which medication direction is correct, or invent evidence.

When medication directions differ, state that the documented directions
differ and that the supplied records do not resolve the difference.

If a home-monitoring log is due at the upcoming visit, absence of an uploaded
log before that visit is not proof of failure. State that the log is not
available for pre-visit verification and remains due at the return visit.

Return ONE JSON object with exactly this top-level structure:
{{
  "items": [
    {{
      "item_id": "...",
      "status": "...",
      "evidence_summary": "...",
      "source_ids": ["..."],
      "reason": "..."
    }}
  ]
}}

The object must have exactly one top-level key: "items".
Do NOT return a bare array.
Do NOT wrap the JSON in markdown or code fences.
Return exactly one items[] entry for every prior plan item.
item_id must match the IDs provided in the chart.
source_ids may contain only source IDs present in the evidence bundle retrieved
for that same item. COMPLETED must cite at least one source ID. NOT FOUND may
have an empty source_ids array.

REVIEW CONTEXT AND RETRIEVED EVIDENCE:
{json.dumps(review_context, indent=2)}
"""

    return call_llm_task(prompt, build_assessment_schema())


def source_ids_for_item(evidence_by_item, item_id):
    ids = set()
    for records in evidence_by_item[item_id]["records"].values():
        for record in records:
            if "source_id" in record:
                ids.add(record["source_id"])
    return ids


def validate_results(chart, agent_result, evidence_by_item):
    expected_ids = {
        item["id"] for item in chart["previous_visit"]["plan_items"]
    }

    actual_ids = [item["item_id"] for item in agent_result["items"]]

    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("Agent returned duplicate plan items.")

    if set(actual_ids) != expected_ids:
        raise ValueError(
            f"Plan-item mismatch. Expected {expected_ids}, got {set(actual_ids)}"
        )

    for item in agent_result["items"]:
        if item["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status: {item['status']}")

        if item["status"] == "COMPLETED" and not item["source_ids"]:
            raise ValueError(
                f"COMPLETED item {item['item_id']} must cite source evidence."
            )

        allowed_sources = source_ids_for_item(
            evidence_by_item, item["item_id"]
        )
        unknown_sources = set(item["source_ids"]) - allowed_sources
        if unknown_sources:
            raise ValueError(
                "Agent cited source IDs outside the retrieved evidence for "
                f"{item['item_id']}: {unknown_sources}"
            )

        item["record_categories_checked"] = evidence_by_item[
            item["item_id"]
        ]["record_categories"]

    return agent_result


def build_source_record_lookup(evidence_by_item):
    lookup = {}
    for evidence in evidence_by_item.values():
        for category, records in evidence["records"].items():
            for record in records:
                source_id = record.get("source_id")
                if source_id:
                    lookup[source_id] = {
                        "record_category": category,
                        "record": record,
                    }
    return lookup


def create_staff_tasks(chart, results):
    plan_lookup = {
        item["id"]: item["text"]
        for item in chart["previous_visit"]["plan_items"]
    }

    tasks = []

    for result in results["items"]:
        status = result["status"]

        if status == "COMPLETED":
            continue

        action_by_status = {
            "PENDING": "Review pending item before visit",
            "NOT FOUND": "Locate or confirm missing record before visit",
            "CONFLICTING": "Reconcile conflicting chart evidence before visit",
            "CANNOT VERIFY": "Verify item with patient or source before visit",
        }
        action_by_item = {
            "metformin": (
                "Flag inconsistent documented directions for clinician or "
                "pharmacist review"
            ),
            "bp_log": (
                "Confirm whether the patient has the requested 7-day log "
                "available to bring"
            ),
        }

        tasks.append(
            {
                "item_id": result["item_id"],
                "status": status,
                "task": action_by_item.get(
                    result["item_id"], action_by_status[status]
                ),
                "plan_item": plan_lookup[result["item_id"]],
            }
        )

    return tasks


def run_careloop(path="data/demo_patient.json", chart=None):
    if chart is None:
        chart = load_chart(path)
    selection = select_evidence(chart)
    evidence_by_item = retrieve_evidence(chart, selection)
    raw_result = call_agent(chart, evidence_by_item)
    validated = validate_results(chart, raw_result, evidence_by_item)
    tasks = create_staff_tasks(chart, validated)

    return {
        "patient": chart["patient"],
        "results": validated["items"],
        "staff_tasks": tasks,
        "source_records": build_source_record_lookup(evidence_by_item),
    }


if __name__ == "__main__":
    print(json.dumps(run_careloop(), indent=2))
