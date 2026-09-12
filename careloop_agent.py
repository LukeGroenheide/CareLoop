import json
import subprocess
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


def build_schema():
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


def call_agent(chart):
    prompt = f"""
You are CareLoop, a pre-visit care-plan verification agent.

Your job is NOT to summarize the chart generally.
For every prior plan item, determine whether what was supposed to happen
actually happened before the upcoming visit.

Use only the supplied synthetic chart evidence.

Status meanings:
COMPLETED = clear evidence the requested action occurred.
PENDING = action exists/in progress but is not complete.
NOT FOUND = expected evidence is absent from the supplied records.
CONFLICTING = supplied records disagree in a way relevant to the plan.
CANNOT VERIFY = evidence suggests something may have happened, but the
requested action cannot actually be verified.

Do not diagnose, recommend treatment, change medications, or invent evidence.

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
source_ids may contain only source IDs actually present in the supplied chart.

CHART:
{json.dumps(chart, indent=2)}
"""

    params = {
        "name": "llm-task",
        "args": {
            "prompt": prompt,
            "thinking": "low",
            "schema": build_schema(),
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


def valid_source_ids(chart):
    ids = set()

    for records in chart.get("records", {}).values():
        for record in records:
            if "source_id" in record:
                ids.add(record["source_id"])

    return ids


def validate_results(chart, agent_result):
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

    allowed_sources = valid_source_ids(chart)

    for item in agent_result["items"]:
        if item["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status: {item['status']}")

        unknown_sources = set(item["source_ids"]) - allowed_sources
        if unknown_sources:
            raise ValueError(
                f"Agent invented source IDs: {unknown_sources}"
            )

    return agent_result


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

        tasks.append(
            {
                "item_id": result["item_id"],
                "status": status,
                "task": action_by_status[status],
                "plan_item": plan_lookup[result["item_id"]],
            }
        )

    return tasks


def run_careloop(path="data/demo_patient.json"):
    chart = load_chart(path)
    raw_result = call_agent(chart)
    validated = validate_results(chart, raw_result)
    tasks = create_staff_tasks(chart, validated)

    return {
        "patient": chart["patient"],
        "results": validated["items"],
        "staff_tasks": tasks,
    }


if __name__ == "__main__":
    print(json.dumps(run_careloop(), indent=2))
