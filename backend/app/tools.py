"""Simulated protected tools + execution-ticket (gateway bypass) enforcement.

Every protected tool implementation in this module refuses to run unless it
receives a valid **execution ticket** signed by the security gateway. The
ticket binds a single (agent, session, tool, params) tuple, so a forged or
replayed ticket — e.g. an agent calling `execute_tool` directly — raises
:class:`GatewayBypassError` and is audited as a bypass attempt.

All data here is simulated and local: no email is sent, no real customer
record is read, no real external transfer ever happens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .config import get_ticket_secret


class GatewayBypassError(Exception):
    """Raised when a tool is invoked without a valid gateway ticket."""


# ---------------------------------------------------------------------------
# Execution tickets
# ---------------------------------------------------------------------------


def _canonical(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def _params_hash(params: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(params).encode("utf-8")).hexdigest()


def _sign(payload: str) -> str:
    return hmac.new(
        get_ticket_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def issue_ticket(agent_id: str, session_id: str, tool: str, params: dict[str, Any]) -> str:
    """Create a single-use execution ticket for one approved action."""
    nonce = uuid.uuid4().hex
    payload = f"{agent_id}|{session_id}|{tool}|{_params_hash(params)}|{nonce}"
    return f"{nonce}.{_sign(payload)}"


def verify_ticket(
    ticket: str, agent_id: str, session_id: str, tool: str, params: dict[str, Any]
) -> None:
    """Validate a ticket; raise GatewayBypassError when it does not match."""
    if not ticket or "." not in ticket:
        raise GatewayBypassError("missing or malformed execution ticket")
    nonce, signature = ticket.split(".", 1)
    payload = f"{agent_id}|{session_id}|{tool}|{_params_hash(params)}|{nonce}"
    expected = _sign(payload)
    if not hmac.compare_digest(signature, expected):
        raise GatewayBypassError(
            "execution ticket signature mismatch (possible gateway bypass)"
        )


# ---------------------------------------------------------------------------
# Simulated environment (local, deterministic, no network)
# ---------------------------------------------------------------------------

DOCUMENTS: dict[str, dict[str, Any]] = {
    "kb/onboarding-guide.md": {
        "title": "Employee Onboarding Guide",
        "classification": "internal",
        "content": "Week 1 checklist, tooling setup and team rituals.",
    },
    "kb/release-runbook.md": {
        "title": "Release Runbook",
        "classification": "internal",
        "content": "How to cut, verify and roll back a release.",
    },
    "kb/partner-faq.md": {
        "title": "Partner FAQ",
        "classification": "confidential",
        "content": "Answers prepared for partner integrations.",
    },
}

CUSTOMER_RECORDS: dict[str, dict[str, Any]] = {
    "cust-001": {
        "id": "cust-001",
        "name": "Ada Lovelace (simulated)",
        "email": "ada@example.test",
        "plan": "enterprise",
        "balance_eur": 12840.55,
        "support_notes": "Requested invoice reissue; card ending 4242 (simulated).",
    },
    "cust-002": {
        "id": "cust-002",
        "name": "Grace Hopper (simulated)",
        "email": "grace@example.test",
        "plan": "pro",
        "balance_eur": 320.0,
        "support_notes": "Churn risk flagged after failed payment (simulated).",
    },
}

OPERATIONAL_RECORD: dict[str, Any] = {
    "record_id": "ops-4711",
    "name": "payment-retry-policy",
    "status": "active",
    "max_retries": 3,
    "rate_limit_rps": 100,
    "version": 1,
    "last_modified_by": "seed",
}

# Simulated side-effect sinks (evidence of execution, never real).
ARTIFACTS: dict[str, dict[str, Any]] = {}
WRITE_LOG: list[dict[str, Any]] = []
OUTBOUND_LOG: list[dict[str, Any]] = []

_lock = threading.Lock()


def reset_simulated_state() -> None:
    """Used by tests to isolate simulated side effects."""
    with _lock:
        ARTIFACTS.clear()
        WRITE_LOG.clear()
        OUTBOUND_LOG.clear()
        OPERATIONAL_RECORD.update(
            {
                "status": "active",
                "max_retries": 3,
                "rate_limit_rps": 100,
                "version": 1,
                "last_modified_by": "seed",
            }
        )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _read_document(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    path = params.get("path")
    doc = DOCUMENTS.get(str(path))
    if not doc:
        raise ValueError(f"document not found: {path}")
    return (
        {
            "path": path,
            "title": doc["title"],
            "classification": doc["classification"],
            "preview": doc["content"][:160],
        },
        False,
        f"Read internal document '{path}'",
    )


def _generate_report(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    artifact_id = f"art-{uuid.uuid4().hex[:10]}"
    title = str(params.get("title", "Untitled report"))
    source = params.get("source")
    classification = params.get("classification", "internal")
    content = f"Report generated from source '{source}'."
    with _lock:
        ARTIFACTS[artifact_id] = {
            "artifact_id": artifact_id,
            "title": title,
            "source": source,
            "classification": classification,
            "content": content,
        }
    return (
        {"artifact_id": artifact_id, "title": title, "classification": classification},
        False,
        f"Generated report artifact {artifact_id}",
    )


def _save_to_destination(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    artifact_id = str(params.get("artifact_id"))
    destination = str(params.get("destination"))
    with _lock:
        artifact = ARTIFACTS.get(artifact_id)
        if not artifact:
            raise ValueError(f"artifact not found: {artifact_id}")
        entry = {
            "artifact_id": artifact_id,
            "destination": destination,
            "title": artifact["title"],
        }
        WRITE_LOG.append(entry)
    return entry, True, f"Saved '{artifact_id}' to {destination}"


def _read_customer_records(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    ids = params.get("record_ids") or []
    found, missing = [], []
    for rid in ids:
        rec = CUSTOMER_RECORDS.get(str(rid))
        (found if rec else missing).append(rec or rid)
    return (
        {"records": found, "missing": missing, "simulated": True},
        False,
        f"Read {len(found)} simulated customer record(s)",
    )


def _aggregate_customer_data(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    fields = params.get("fields") or ["balance_eur"]
    ids = params.get("record_ids") or list(CUSTOMER_RECORDS)
    rows = [CUSTOMER_RECORDS[i] for i in ids if i in CUSTOMER_RECORDS]

    totals: dict[str, Any] = {}
    for field_name in fields:
        values = [r.get(field_name) for r in rows]
        numbers: list[float] = []
        numeric = True
        for value in values:
            try:
                numbers.append(float(value))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                numeric = False
                break
        if numeric and numbers:
            totals[field_name] = round(sum(numbers), 2)
        else:
            totals[field_name] = {
                "distinct": len({str(v) for v in values}),
                "populated": sum(1 for v in values if v is not None),
            }
    return (
        {
            "row_count": len(rows),
            "totals": totals,
            "includes_contact_details": "email" in fields,
            "simulated": True,
        },
        False,
        f"Aggregated {len(rows)} simulated customer records",
    )


def _create_summary(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    artifact_id = f"sum-{uuid.uuid4().hex[:10]}"
    includes = params.get("includes") or []
    contains_pii = bool(params.get("contains_pii")) or any(
        key in includes for key in ("email", "balance", "support_notes", "name")
    )
    sensitivity = "restricted" if contains_pii else "confidential"
    summary_text = "Summary of customer findings (simulated)."
    with _lock:
        ARTIFACTS[artifact_id] = {
            "artifact_id": artifact_id,
            "title": params.get("title", "Customer summary"),
            "classification": sensitivity,
            "content": summary_text,
            "includes": includes,
            "contains_pii": contains_pii,
        }
    return (
        {
            "artifact_id": artifact_id,
            "sensitivity": sensitivity,
            "contains_pii": contains_pii,
        },
        False,
        f"Created {sensitivity} summary {artifact_id}",
    )


def _transfer_external(params: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    """Simulated outbound transfer — writes to a local log only, no network."""
    artifact_id = str(params.get("artifact_id"))
    destination = str(params.get("destination"))
    with _lock:
        artifact = ARTIFACTS.get(artifact_id)
        if not artifact:
            raise ValueError(f"artifact not found: {artifact_id}")
        entry = {
            "transfer_id": uuid.uuid4().hex[:12],
            "artifact_id": artifact_id,
            "destination": destination,
            "simulated": True,
        }
        OUTBOUND_LOG.append(entry)
    return entry, True, f"Transferred {artifact_id} to {destination} (simulated)"


def _propose_record_modification(
    params: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    proposal_id = f"prop-{uuid.uuid4().hex[:10]}"
    return (
        {
            "proposal_id": proposal_id,
            "record_id": params.get("record_id"),
            "changes": params.get("changes", {}),
            "state": "proposed",
        },
        False,
        f"Proposed modification to {params.get('record_id')} (no side effect yet)",
    )


def _modify_operational_record(
    params: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """Protected write: only reachable through an approved gateway ticket."""
    record_id = str(params.get("record_id"))
    changes = dict(params.get("changes") or {})
    with _lock:
        if record_id != OPERATIONAL_RECORD["record_id"]:
            raise ValueError(f"operational record not found: {record_id}")
        for key, value in changes.items():
            OPERATIONAL_RECORD[key] = value
        OPERATIONAL_RECORD["version"] += 1
        OPERATIONAL_RECORD["last_modified_by"] = params.get("requested_by", "unknown")
        snapshot = dict(OPERATIONAL_RECORD)
    return snapshot, True, f"Modified operational record {record_id}"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    side_effect: bool
    protected: bool
    handler: Callable[[dict[str, Any]], tuple[dict[str, Any], bool, str]]


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec("read_document", "Read an internal knowledge-base document", False, False, _read_document),
        ToolSpec("generate_report", "Generate a report artifact", False, False, _generate_report),
        ToolSpec("save_to_destination", "Persist an artifact to a destination", True, False, _save_to_destination),
        ToolSpec("read_customer_records", "Read simulated customer records", False, True, _read_customer_records),
        ToolSpec("aggregate_customer_data", "Aggregate simulated customer data", False, True, _aggregate_customer_data),
        ToolSpec("create_summary", "Create a summary artifact", False, True, _create_summary),
        ToolSpec("transfer_external", "Send an artifact to an external destination", True, True, _transfer_external),
        ToolSpec("propose_record_modification", "Propose a protected record change", False, True, _propose_record_modification),
        ToolSpec("modify_operational_record", "Apply a protected operational change", True, True, _modify_operational_record),
    ]
}


def execute_tool(
    tool: str,
    params: dict[str, Any],
    *,
    agent_id: str,
    session_id: str,
    ticket: str,
) -> dict[str, Any]:
    """Execute a protected tool — refuses to run without a valid ticket.

    This is the only place simulated side effects happen. Anything that
    reaches here without a gateway-issued ticket raises
    :class:`GatewayBypassError`.
    """
    spec = TOOLS.get(tool)
    if spec is None:
        raise ValueError(f"unknown tool: {tool}")
    verify_ticket(ticket, agent_id, session_id, tool, params)
    result, side_effect, summary = spec.handler(params)
    return {
        "tool": tool,
        "result": result,
        "side_effect": side_effect,
        "summary": summary,
    }


def list_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "side_effect": t.side_effect,
            "protected": t.protected,
        }
        for t in TOOLS.values()
    ]
