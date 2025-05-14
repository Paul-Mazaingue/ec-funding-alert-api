from typing import Any, Dict, List, Optional

# Type aliases for better readability
QueryClause = Dict[str, Any]
QueryClauseList = List[QueryClause]

# Constants
DEFAULT_TYPES = ["1", "2", "8"]
DEFAULT_STATUSES = ["31094501", "31094502", "31094503"]
DEFAULT_OPERATOR = "AND"

# Available text search fields
TEXT_SEARCH_FIELDS = [
    "identifier", "keywords", "tags", "typesOfAction", "title",
    "callTitle", "projectAcronym", "projectName", "description",
    "furtherInformation", "missionDescription", "missionDetails",
    "destinationDescription", "destinationDetails", "duration"
]


def add_terms_clause(field: str, values: List[str], must_clauses: QueryClauseList) -> None:
    """
    Add a terms clause to the must_clauses list.
    
    Args:
        field: The field name to query
        values: List of values to match against
        must_clauses: List to append the clause to
    """
    must_clauses.append({"terms": {field: values}})


def add_text_clause(field: str, query: str, must_clauses: QueryClauseList) -> None:
    """
    Add a text clause to the must_clauses list.
    
    Args:
        field: The field name to query
        query: Query text to search for
        must_clauses: List to append the clause to
    """
    must_clauses.append({
        "text": {
            "query": query,
            "fields": [field],
            "defaultOperator": DEFAULT_OPERATOR
        }
    })


def add_range_clause(field: str, range_values: Dict[str, int], must_clauses: QueryClauseList) -> None:
    """
    Add a range clause to the must_clauses list.
    
    Args:
        field: The field name to query
        range_values: Dictionary with 'gte' and/or 'lte' keys
        must_clauses: List to append the clause to
    """
    range_query: QueryClause = {"range": {field: {}}}
    
    if "gte" in range_values and range_values["gte"] is not None:
        range_query["range"][field]["gte"] = range_values["gte"]
    if "lte" in range_values and range_values["lte"] is not None:
        range_query["range"][field]["lte"] = range_values["lte"]
        
    must_clauses.append(range_query)


def add_text_search_clause(text_search: str, fields: List[str], must_clauses: QueryClauseList) -> None:
    """
    Add a text search clause that matches multiple fields.
    
    Args:
        text_search: Text to search for
        fields: List of fields to search in
        must_clauses: List to append the clause to
    """
    should_clauses = [{"phrase": {"query": text_search, "field": field}} for field in fields]
    must_clauses.append({"bool": {"should": should_clauses}})


def generate_query(
    types: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    framework_programmes: Optional[List[str]] = None,
    call_identifier: Optional[str] = None,
    starting_date_range: Optional[Dict[str, int]] = None,
    deadline_range: Optional[Dict[str, int]] = None,
    text_search: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a structured query for the EC API.
    
    Args:
        types: List of types to filter by
        statuses: List of statuses to filter by
        framework_programmes: Framework programmes to search for
        call_identifier: Call identifier to search for
        starting_date_range: Range for starting date
        deadline_range: Range for deadline date
        text_search: General text to search across multiple fields
        
    Returns:
        Structured query object ready for the API
    """
    must_clauses: QueryClauseList = []

    # Apply default values if not provided
    types = types or DEFAULT_TYPES
    statuses = statuses or DEFAULT_STATUSES

    # Add required filters
    add_terms_clause("type", types, must_clauses)
    add_terms_clause("status", statuses, must_clauses)

    # Add optional filters if provided
    if framework_programmes:
        add_text_clause("frameworkProgramme", framework_programmes, must_clauses)
        
    if call_identifier:
        add_text_clause("callIdentifier", call_identifier, must_clauses)
        
    if starting_date_range and (starting_date_range.get("gte") or starting_date_range.get("lte")):
        add_range_clause("startDate", starting_date_range, must_clauses)
        
    if deadline_range and (deadline_range.get("gte") or deadline_range.get("lte")):
        add_range_clause("deadlineDate", deadline_range, must_clauses)
        
    if text_search:
        add_text_search_clause(text_search, TEXT_SEARCH_FIELDS, must_clauses)

    # Compile the final query
    return {"bool": {"must": must_clauses}}