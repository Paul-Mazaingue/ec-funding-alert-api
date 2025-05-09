import json
from typing import List, Optional, Dict

def generate_query(
    types: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    framework_programmes: Optional[List[str]] = None,
    call_identifier: Optional[str] = None,
    starting_date_range: Optional[Dict[str, int]] = None,
    deadline_range: Optional[Dict[str, int]] = None,
    text_search: Optional[str] = None
) -> Dict:
    must_clauses = []

    # Default values
    if not types:
        types = ["1", "2", "8"]
    if not statuses:
        statuses = ["31094501", "31094502", "31094503"]

    must_clauses.append({"terms": {"type": types}})
    must_clauses.append({"terms": {"status": statuses}})

    if framework_programmes:
        must_clauses.append({"terms": {"frameworkProgramme": framework_programmes}})
    if call_identifier:
        must_clauses.append({"term": {"callIdentifier": call_identifier}})
    if starting_date_range:
        must_clauses.append({"range": {"startDate": starting_date_range}})
    if deadline_range:
        must_clauses.append({"range": {"deadline": deadline_range}})

    if text_search:
        text_fields = [
            "identifier", "keywords", "tags", "typesOfAction", "title",
            "callTitle", "projectAcronym", "projectName", "description",
            "furtherInformation", "missionDescription", "missionDetails",
            "destinationDescription", "destinationDetails", "duration"
        ]
        should_clauses = [{"phrase": {"query": text_search, "field": field}} for field in text_fields]

        must_clauses.append({"bool": {"should": should_clauses}})

    return {"bool": {"must": must_clauses}}



print("This module is not meant to be run directly.")
# Example usage
query = generate_query(
    text_search="Digital"
)
print("Generated Query:")
print(json.dumps(query, indent=4))