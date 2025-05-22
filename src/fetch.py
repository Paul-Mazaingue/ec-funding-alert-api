import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .facet import get_value_from_rawValue
from .request import request_api_async
from .utils import load_json, save_json

# =========================
# Configuration & Constants
# =========================

# API configuration
API_URL: str = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_PARAMS: Dict[str, str] = {"apiKey": "SEDIA", "text": "***"}

# Request configuration
SIMULTANEOUS_REQUESTS: int = 10
PAGE_SIZE: int = 100
DATAFOLDER: str = "data"
ALERTS_SUBFOLDER: str = f"{DATAFOLDER}/alerts"

# Type mappings
TYPE_MAPPINGS: Dict[str, str] = {
    "1": "Direct calls for proposals (issued by the EU)",
    "2": "EU External Actions",
    "8": "Cascade funding"
}

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================
# Utility & Helper Functions
# ===========================

def filter_results_by_keywords(
    results: List[Dict[str, Any]], 
    keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter results based on the presence or absence of keywords in the 'descriptionByte' field.
    If a keyword starts with '!', exclude results containing that keyword.
    
    Args:
        results: List of API results to filter
        keywords: List of keywords to search for (prefix '!' to exclude)
        
    Returns:
        Filtered list of results
    """
    if not keywords:
        return results

    include_keywords = [k.lower() for k in keywords if not k.startswith("!")]
    exclude_keywords = [k[1:].lower() for k in keywords if k.startswith("!")]

    filtered: List[Dict[str, Any]] = []
    for result in results:
        metadata = result.get("metadata", {})
        description = metadata.get("descriptionByte")

        if description is None:
            filtered.append(result)
            continue

        # Normalize description to string
        if isinstance(description, list):
            description_text = " ".join(description).lower()
        else:
            description_text = str(description).lower()

        # Exclude if any exclude keyword is present
        if any(ex_kw in description_text for ex_kw in exclude_keywords):
            continue

        # If include keywords are specified, include only if at least one is present
        if include_keywords:
            if any(in_kw in description_text for in_kw in include_keywords):
                filtered.append(result)
        else:
            # No include keywords, so include all that passed the exclude filter
            filtered.append(result)

    return filtered


def add_identifiers_to_query(
    query: Dict[str, Any], 
    identifiers: str
) -> Dict[str, Any]:
    """
    Add identifiers to the query for filtering.
    
    Args:
        query: Original query object
        identifiers: Comma-separated list of identifiers
        
    Returns:
        Query with added identifier filters
    """
    if not query:
        return {}
    if not identifiers:
        return query

    # Make a deep copy of the query to avoid modifying the original
    query_copy = json.loads(json.dumps(query))
    
    identifiers_list = [identifier.strip() for identifier in identifiers.split(",") if identifier.strip()]
    for identifier in identifiers_list:
        query_copy.setdefault("bool", {}).setdefault("must", []).append({
            "text": {
                "query": identifier,
                "fields": ["identifier"],
                "defaultOperator": "AND"
            }
        })
    return query_copy


def format_date(date_str: Optional[Union[str, list]]) -> str:
    """
    Format a date string from API format to 'dd-mm-yyyy'.
    
    Args:
        date_str: Date string or list of date strings from API
        
    Returns:
        Formatted date string or empty string if parsing fails
    """
    if not date_str:
        return ""
        
    if isinstance(date_str, list):
        date_str = date_str[0]
        
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f%z")
        return date_obj.strftime("%d-%m-%Y")
    except Exception:
        return str(date_str)


def map_type(type_code: str) -> str:
    """
    Maps type codes to human-readable descriptions.
    
    Args:
        type_code: Type code from the API
        
    Returns:
        Human-readable description of the type
    """
    return TYPE_MAPPINGS.get(type_code, "Other")


# ===========================
# Main Fetching Functionality
# ===========================

async def fetch_all_calls(alert: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch all calls from the API, filtered by keywords if provided.
    
    Args:
        alert: Alert configuration containing file paths and keywords
        
    Returns:
        List of dicts with 'reference' and 'identifier' or None if failed
    """
    keywords: List[str] = alert.get("keywords", [])
    all_refs: List[Dict[str, Any]] = []

    try:
        response = await request_api_async(API_URL, API_PARAMS, alert.get("file_paths", {}))
    except Exception as e:
        logger.error(f"Initial API request failed: {e}", exc_info=True)
        return None

    if not response:
        logger.warning("No response received from initial API request.")
        return None

    total_results: int = response.get("totalResults", 0)
    # Store total results in the alert object for later use
    alert["totalResults"] = total_results
    total_pages: int = (total_results + PAGE_SIZE - 1) // PAGE_SIZE

    logger.info(f"Total results: {total_results}, Pages to fetch: {total_pages}")

    # Use a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(SIMULTANEOUS_REQUESTS)

    async def fetch_page(page: int) -> List[Dict[str, Any]]:
        """Fetch a single page of results."""
        async with semaphore:
            paged_params = API_PARAMS.copy()
            paged_params.update({"pageNumber": page, "pageSize": PAGE_SIZE})
            try:
                resp = await request_api_async(API_URL, paged_params, alert.get("file_paths", {}))
            except Exception as e:
                logger.error(f"API request for page {page} failed: {e}")
                return []
            if not resp:
                logger.error(f"Page {page} returned no response.")
                return []
                
            logger.info(f"Fetched page {page}/{total_pages}")
            results = resp.get("results", [])
            filtered_results = filter_results_by_keywords(results, keywords)
            
            return [
                {
                    "reference": result.get("reference"),
                    "identifier": result.get("metadata", {}).get("identifier"),
                    "page": page # temporary for debugging
                }
                for result in filtered_results
                if result.get("reference") and result.get("metadata", {}).get("identifier")
            ]

    # Prepare and run all page fetch tasks concurrently
    tasks = [fetch_page(page) for page in range(1, total_pages + 1)]
    try:
        pages_results = await asyncio.gather(*tasks)
    except Exception as e:
        logger.error(f"Error during page fetching: {e}", exc_info=True)
        return None

    # If any page failed (empty list), return None
    if any(page_results == [] for page_results in pages_results):
        logger.error("At least one page failed to fetch. Returning None.")
        return None

    # Combine all page results
    for page_results in pages_results:
        all_refs.extend(page_results)

    # vérification pour vérifier si des références sont en double
    unique_refs = {ref["reference"]: ref for ref in all_refs}
    
    logger.info(f"Fetched {len(unique_refs)} unique references. total: {len(all_refs)}")
    if len(unique_refs) != len(all_refs):
        # print page number of the duplicates
        duplicates = {ref["reference"]: ref for ref in all_refs if ref["reference"] not in unique_refs}
        logger.warning(f"Duplicate references found: {duplicates}")
        logger.warning("Duplicate references found. Keeping only unique ones.")
        all_refs = list(unique_refs.values())

    # Pause to avoid API saturation
    await asyncio.sleep(1)

    logger.info(f"Total calls fetched: {len(all_refs)}")
    return all_refs


async def get_detailed_info(
    identifier: str, 
    reference: str, 
    alert: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed information for a specific call.
    
    Args:
        identifier: Call identifier
        reference: Call reference
        alert: Alert configuration
        
    Returns:
        Detailed information for the call or None if failed
    """
    # Create alerts directory if it doesn't exist
    os.makedirs(ALERTS_SUBFOLDER, exist_ok=True)
    
    # Prepare a unique temporary query file path
    unique_id = str(uuid.uuid4())[:8]
    tmp_query_path = f"{ALERTS_SUBFOLDER}/{alert.get('name')}_{unique_id}_query_tmp.json"
    
    logger.info(f"Preparing temporary file {tmp_query_path}")
    
    try:
        # Get the query from file or alert configuration
        query = _load_query(alert)
        if not query:
            return None
            
        # Add the identifier to the query
        query = add_identifiers_to_query(query, identifier)
        
        # Save the modified query to the temporary file
        if not _save_temp_query(query, tmp_query_path):
            return None
            
        # Prepare file paths for the API request
        file_paths = _prepare_file_paths(alert, tmp_query_path)
            
        # Perform the API request and process results
        return await _fetch_and_process_results(file_paths, identifier, reference)
            
    except Exception as e:
        logger.error(f"Error in get_detailed_info: {e}", exc_info=True)
        return None
    finally:
        # Always try to clean up the temporary file
        _cleanup_temp_file(tmp_query_path)


def _load_query(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Load query from file path or alert configuration."""
    query_path = alert.get("file_paths", {}).get('query', '')
    query = None
    
    if os.path.exists(query_path):
        query = load_json(query_path)
        logger.info(f"Query loaded from {query_path}")
    
    # If query file doesn't exist or is invalid, try the query from the alert
    if not query:
        logger.warning(f"Query file {query_path} not found or invalid, using alert's query")
        query = alert.get("query", {})
    
    # If still no query, we cannot proceed
    if not query:
        logger.error("No query found for the alert.")
        return None
        
    return query


def _save_temp_query(query: Dict[str, Any], tmp_query_path: str) -> bool:
    """Save modified query to temporary file."""
    logger.info(f"Saving modified query to {tmp_query_path}")
    if not save_json(query, tmp_query_path):
        logger.error(f"Error saving temporary file {tmp_query_path}")
        return False
    
    # Verify the file was created successfully
    if not os.path.exists(tmp_query_path):
        logger.error(f"Temporary file {tmp_query_path} was not created properly")
        return False
        
    logger.info(f"Temporary file {tmp_query_path} created successfully")
    return True


def _prepare_file_paths(alert: Dict[str, Any], tmp_query_path: str) -> Dict[str, str]:
    """Prepare file paths for API request."""
    return {
        'query': tmp_query_path,
        'languages': alert.get("file_paths", {}).get('languages', 'config/languages.json'),
        'sort': alert.get("file_paths", {}).get('sort', 'config/sort.json')
    }


def _cleanup_temp_file(file_path: str) -> None:
    """Clean up temporary query file."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Temporary file {file_path} deleted successfully")
        except Exception as e:
            logger.warning(f"Failed to delete temporary file {file_path}: {e}")


async def _fetch_and_process_results(
    file_paths: Dict[str, str],
    identifier: str,
    reference: str
) -> Optional[Dict[str, Any]]:
    """Fetch results from API and process them."""
    # Make the initial API request
    response = await request_api_async(API_URL, API_PARAMS, file_paths)
    
    if not response:
        logger.warning("No response received from API request.")
        return None
    
    total_results: int = response.get("totalResults", 0)
    total_pages: int = (total_results + PAGE_SIZE - 1) // PAGE_SIZE
    
    results: List[Dict[str, Any]] = []
    
    # Fetch all pages
    for page in range(1, total_pages + 1):
        params_copy = API_PARAMS.copy()
        params_copy.update({"pageNumber": page, "pageSize": PAGE_SIZE})
        
        try:
            # Verify the temporary file still exists before each request
            if not os.path.exists(file_paths['query']):
                logger.error(f"Temporary file {file_paths['query']} disappeared before page {page} request")
                return None
                
            page_response = await request_api_async(API_URL, params_copy, file_paths)
            if not page_response:
                logger.error(f"Page {page} returned no response.")
                continue
            
            logger.info(f"Fetched page {page}/{total_pages}")
            results.extend(page_response.get("results", []))
        except Exception as e:
            logger.error(f"API request for page {page} failed: {e}")
            continue
            
    # Process results
    for res in results:
        if res.get("reference") == reference:
            return _extract_call_details(res, identifier)
    
    logger.warning(f"No result found matching reference {reference}")
    return None


def _extract_call_details(result: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    """Extract and format call details from API result."""
    metadata = result.get("metadata", {})
    
    # Determine the URL format
    call_url = result.get("url", "")
    if call_url.endswith(".json"):
        full_url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier}"
    else:
        callccm2 = _get_first_value(metadata.get("callccm2Id"))
        full_url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/competitive-calls-cs/{callccm2}"
    
    return {
        "title": metadata.get("title"),
        "starting_date": format_date(metadata.get("startDate")),
        "deadline": format_date(metadata.get("deadlineDate")),
        "type": map_type(_get_first_value(metadata.get("type"))),
        "status": get_value_from_rawValue(_get_first_value(metadata.get("status")), "status"),
        "frameworkProgramme": get_value_from_rawValue(_get_first_value(metadata.get("frameworkProgramme")), "frameworkProgramme"),
        "url": full_url,
        "identifier": identifier,
        "reference": result.get("reference"),
        "summary": result.get("summary"),
        "keywords": metadata.get("keywords"),
        "destination": get_value_from_rawValue(_get_first_value(metadata.get("destination")), "destination"),
        "focusArea": get_value_from_rawValue(_get_first_value(metadata.get("focusArea")), "focusArea"),
        "destinationDetails": metadata.get("destinationDetails"),
        "destinationGroup": get_value_from_rawValue(_get_first_value(metadata.get("destinationGroup")), "destinationGroup"),
        "callTitle": metadata.get("callTitle"),
        "descriptionByte": metadata.get("descriptionByte"),
        "programmeDivision": get_value_from_rawValue(_get_first_value(metadata.get("programmeDivision")), "programmeDivision"),
        "crossCuttingPriorities": metadata.get("crossCuttingPriorities"),
        "typesOfAction": metadata.get("typesOfAction"),
        "tags": metadata.get("tags")
    }


def _get_first_value(value: Any) -> str:
    """Safely extract the first value from a list or return the value itself."""
    if isinstance(value, list) and value:
        return value[0]
    return value or ""

async def get_total_results(alert: Dict[str, Any]) -> int:
    """
    Get the total number of results from the API.
    
    Args:
        alert: Alert configuration containing file paths and keywords
        
    Returns:
        Total number of results or 0 if failed
    """
    try:
        # check if query file exists else create it
        file_paths = alert.get("file_paths", {})
        if isinstance(file_paths, dict):
            query_path = file_paths.get('query', '')
        else:
            query_path = file_paths if isinstance(file_paths, str) else ''
        
        query = alert.get("query", {})
        if not save_json(query, query_path):
            logger.error(f"Error saving query to {query_path}")
            return 0
        response = await request_api_async(API_URL, API_PARAMS, alert.get("file_paths", {}))
        total_results = response.get("totalResults", 0) if response else 0
        logger.info(f"Total results for alert '{alert.get('name')}': {total_results}")
        return total_results
    except Exception as e:
        logger.error(f"Error fetching total results: {e}", exc_info=True)
        return 0