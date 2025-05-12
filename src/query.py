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
        must_clauses.append({
            "text": {
                    "query": framework_programmes,
                    "fields": ["frameworkProgramme"],
                    "defaultOperator": "AND"
                }
        })
        #must_clauses.append({"terms": {"frameworkProgramme": framework_programmes}})
    if call_identifier:
        must_clauses.append({
            "text": {
                    "query": call_identifier,
                    "fields": ["callIdentifier"],
                    "defaultOperator": "AND"
                }
        })
        #must_clauses.append({"term": {"callIdentifier": call_identifier}})
    if starting_date_range:
        range_query = {
            "range": {
                "startDate": {}
            }
        }
        if starting_date_range.get("gte"):
            range_query["range"]["startDate"]["gte"] = starting_date_range["gte"]
        if starting_date_range.get("lte"):
            range_query["range"]["startDate"]["lte"] = starting_date_range["lte"]
        must_clauses.append(range_query)
        #must_clauses.append({"range": {"startDate": starting_date_range}})
    if deadline_range:
        range_query = {
            "range": {
                "deadlineDate": {}
            }
        }
        if deadline_range.get("gte"):
            range_query["range"]["deadlineDate"]["gte"] = deadline_range["gte"]
        if deadline_range.get("lte"):
            range_query["range"]["deadlineDate"]["lte"] = deadline_range["lte"]
        must_clauses.append(range_query)

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

#print("Query Generation Script")

# Example usage
#query = generate_query(
#    text_search="Digital",
#    framework_programmes="43108390",
#    call_identifier="HORIZON-CL5-2024-D3-01",
#    starting_date_range={"gte": "1672441200000", "lte":"1710889200000"},
#    deadline_range={"gte":"1704063600000", "lte":"1713304800000"},
#    statuses=["31094502", "31094503"],
#    types=["1","2"]
#)
#print("Generated Query:")
#print(json.dumps(query, indent=4))