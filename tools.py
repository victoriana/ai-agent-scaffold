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
