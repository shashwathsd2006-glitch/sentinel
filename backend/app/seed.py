"""Seed data: registered agents (idempotent)."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import Agent

AGENTS = [
    {
        "id": "report-agent",
        "name": "Report Agent",
        "role": "internal-analyst",
        "clearance": "internal",
        "granted_tools": [
            "read_document",
            "generate_report",
            "save_to_destination",
        ],
        "description": (
            "Reads internal knowledge-base documents and produces internal "
            "reports. No access to customer records."
        ),
    },
    {
        "id": "support-agent",
        "name": "Support Agent",
        "role": "customer-support",
        "clearance": "restricted",
        "granted_tools": [
            "read_document",
            "read_customer_records",
            "aggregate_customer_data",
            "create_summary",
            "save_to_destination",
            "transfer_external",
        ],
        "description": (
            "Handles support tickets with access to simulated customer "
            "records. External transfers still pass the cumulative-risk gate."
        ),
    },
    {
        "id": "ops-agent",
        "name": "Operations Agent",
        "role": "ops-automation",
        "clearance": "confidential",
        "granted_tools": [
            "read_document",
            "propose_record_modification",
            "modify_operational_record",
            "save_to_destination",
        ],
        "description": (
            "Maintains operational records. Protected modifications always "
            "require human approval."
        ),
    },
]


def seed_reference_data(db: Session) -> None:
    for spec in AGENTS:
        existing = db.get(Agent, spec["id"])
        if existing is None:
            db.add(
                Agent(
                    id=spec["id"],
                    name=spec["name"],
                    role=spec["role"],
                    clearance=spec["clearance"],
                    granted_tools=json.dumps(spec["granted_tools"]),
                    description=spec["description"],
                )
            )
        else:
            existing.granted_tools = json.dumps(spec["granted_tools"])
            existing.description = spec["description"]
    db.flush()
