'''
from langchain_core.tools import tool

@tool
def search_hr_policy(query: str) -> str:
    """Search the internal HR policy database for specific clauses."""
    # Simulate MCP tool call structure
    return f"Results for: {query}"

@tool
def get_employee_info(user_id: str) -> str:
    """Retrieve employee role and department for context-aware answers."""
    return f"User {user_id} is in Engineering."
'''
# tools.py: MCP-Compatible Tool Registry & JSON-RPC Dispatcher
import logging
from typing import Any, Callable

logger = logging.getLogger("employee-tools")


# --- User-Scoped Internal Enterprise Tools ---
def get_pto_balance(employee_id: str, user_role: str) -> dict[str, Any]:
    """Fetch remaining PTO hours for an employee."""
    logger.info(f"[TOOL] get_pto_balance(employee_id={employee_id}, role={user_role})")
    balances = {"EMP-101": 88, "EMP-202": 40}
    hours = balances.get(employee_id.upper(), 0)
    return {"employee_id": employee_id.upper(), "pto_hours_remaining": hours}


def check_expense_status(claim_id: str, user_role: str) -> dict[str, Any]:
    """Check reimbursement status for an expense claim."""
    logger.info(f"[TOOL] check_expense_status(claim_id={claim_id}, role={user_role})")
    claims = {"EXP-500": "Approved - Scheduled for Friday payroll", "EXP-501": "Pending Manager Review"}
    return {"claim_id": claim_id.upper(), "status": claims.get(claim_id.upper(), "Not Found")}


# --- MCP Tool Definitions (Standard JSON Schema format) ---
MCP_TOOLS_LIST = [
    {
        "name": "get_pto_balance",
        "description": "Retrieve remaining PTO balance in hours for an employee ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "check_expense_status",
        "description": "Look up the reimbursement status of an expense claim ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"claim_id": {"type": "string"}},
            "required": ["claim_id"],
        },
    },
]

TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_pto_balance": get_pto_balance,
    "check_expense_status": check_expense_status,
}


def mcp_call_tool(tool_name: str, arguments: dict[str, Any], user_role: str) -> dict[str, Any]:
    """Executes a tool call following MCP tools/call semantics with user-scoped RBAC."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        raise ValueError(f"Unknown MCP tool: {tool_name}")
    return handler(**arguments, user_role=user_role)
