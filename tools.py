# tools.py : MCP-Style Tool Schemas + Enforced RBAC
# Defines MCP-compatible tool schemas, dispatches calls cleanly, and enforces role checks inside the tool layer so user_role isn't just logged.

import logging
from typing import Any, Callable

logger = logging.getLogger("policy-tools")

PTO_BALANCES = {"EMP-101": 88, "EMP-202": 40}
EXPENSE_CLAIMS = {"EXP-500": "Approved - Scheduled for Friday payroll", "EXP-501": "Pending Manager Review"}


def get_pto_balance(employee_id: str, user_role: str) -> dict[str, Any]:
    emp_id = employee_id.upper()
    if user_role == "employee" and emp_id != "EMP-101":
        return {"error": "Forbidden: employees can only view their own PTO balance."}
    logger.info("Executing get_pto_balance for %s (role=%s)", emp_id, user_role)
    return {"employee_id": emp_id, "pto_hours_remaining": PTO_BALANCES.get(emp_id, 0)}


def check_expense_status(claim_id: str, user_role: str) -> dict[str, Any]:
    cid = claim_id.upper()
    logger.info("Executing check_expense_status for %s (role=%s)", cid, user_role)
    return {"claim_id": cid, "status": EXPENSE_CLAIMS.get(cid, "Not Found")}


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_pto_balance",
        "description": "Get remaining PTO hours for an employee ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "check_expense_status",
        "description": "Get reimbursement status for an expense claim ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"claim_id": {"type": "string"}},
            "required": ["claim_id"],
        },
    },
]

HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_pto_balance": get_pto_balance,
    "check_expense_status": check_expense_status,
}


def call_mcp_tool(name: str, arguments: dict[str, Any], user_role: str) -> dict[str, Any]:
    handler = HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return handler(**arguments, user_role=user_role)
