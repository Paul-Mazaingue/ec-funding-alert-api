import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from .request import request_api_async
from .utils import load_json

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API endpoints and parameters
FACET_API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/facet"
FACET_API_PARAMS = {"apiKey": "SEDIA", "text": "***"}

# File paths configuration
CONFIG_PATHS = {
    'query': 'config/facet.json',
    'languages': 'config/languages.json'
}
FACET_DATA_PATH = 'data/facet.json'

# Type definitions
FacetEntry = Dict[str, str]
FacetList = List[Dict[str, List[FacetEntry]]]


def transform_facets(data: Dict[str, Any], output_file: str) -> None:
    """
    Transforms facet data into a simplified format and saves it to a JSON file.
    
    Args:
        data: Raw facet data from the API
        output_file: Path to save the transformed data
    """
    output: FacetList = []
    
    for facet in data.get('facets', []):
        name = facet.get('name')
        if not name:
            logger.warning("Facet without a name was ignored.")
            continue
            
        entries = [
            {
                "rawValue": value.get("rawValue"),
                "value": value.get("value")
            }
            for value in facet.get("values", [])
            if "rawValue" in value and "value" in value
        ]
        
        output.append({name: entries})

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        logger.info(f"Facets transformed and saved to {output_file}")
    except Exception as e:
        logger.error(f"Error saving file {output_file}: {e}")


async def request_facet_api(output_file: str = FACET_DATA_PATH) -> bool:
    """
    Calls the facet API and saves the transformed response to a file.
    
    Args:
        output_file: Path to save the transformed data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        result = await request_api_async(FACET_API_URL, FACET_API_PARAMS, CONFIG_PATHS)
    except Exception as e:
        logger.error(f"Error calling API: {e}", exc_info=True)
        return False

    if not result:
        logger.error("No results received from API.")
        return False
        
    transform_facets(result, output_file)
    return True


def _load_facet_data(filepath: str = FACET_DATA_PATH) -> Optional[FacetList]:
    """
    Loads facet data from a JSON file.
    
    Args:
        filepath: Path to the facet data file
        
    Returns:
        List of facet entries or None if loading failed
    """
    try:
        if not os.path.exists(filepath):
            logger.warning(f"Facet data file {filepath} not found.")
            return None
            
        return load_json(filepath)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}", exc_info=True)
        return None


def get_value_from_rawValue(rawValue: str, facet_name: str) -> Optional[str]:
    """
    Returns the readable value associated with a rawValue for a given facet.
    
    Args:
        rawValue: The raw value to look up
        facet_name: Name of the facet to search in
        
    Returns:
        The human-readable value, the original rawValue if not found, or None on error
    """
    facet_data = _load_facet_data()
    if not facet_data:
        logger.error("No facet data available.")
        return None
        
    # Find the facet by name
    facet_entry = _find_facet_by_name(facet_data, facet_name)
    if not facet_entry:
        return None
        
    # Find the value with matching rawValue
    for item in facet_entry[facet_name]:
        if item.get('rawValue') == rawValue:
            return item.get('value')
            
    logger.warning(f"rawValue '{rawValue}' not found for facet '{facet_name}'")
    return rawValue


def get_rawValue_from_value(value: str, facet_name: str) -> Optional[str]:
    """
    Returns the rawValue associated with a readable value for a given facet.
    
    Args:
        value: The human-readable value to look up
        facet_name: Name of the facet to search in
        
    Returns:
        The raw value, the original value if not found, or None on error
    """
    facet_data = _load_facet_data()
    if not facet_data:
        logger.error("No facet data available.")
        return None
        
    # Find the facet by name
    facet_entry = _find_facet_by_name(facet_data, facet_name)
    if not facet_entry:
        return None
        
    # Find the rawValue with matching value
    for item in facet_entry[facet_name]:
        if item.get('value') == value:
            return item.get('rawValue')
            
    logger.warning(f"Value '{value}' not found for facet '{facet_name}'")
    return value


def get_all_values(facet_name: str) -> List[str]:
    """
    Returns all readable values for a given facet.
    
    Args:
        facet_name: Name of the facet to get values from
        
    Returns:
        List of all human-readable values for the facet, or empty list on error
    """
    facet_data = _load_facet_data()
    if not facet_data:
        logger.error("No facet data available.")
        return []
        
    facet_entry = _find_facet_by_name(facet_data, facet_name)
    if not facet_entry:
        return []
        
    return [item.get('value') for item in facet_entry[facet_name] if 'value' in item]


def _find_facet_by_name(facet_data: FacetList, facet_name: str) -> Optional[Dict[str, List[FacetEntry]]]:
    """
    Helper function to find a facet by name in the facet data.
    
    Args:
        facet_data: List of facet entries
        facet_name: Name of the facet to find
        
    Returns:
        The facet entry or None if not found
    """
    facet_entry = next((item for item in facet_data if facet_name in item), None)
    if not facet_entry:
        logger.error(f"Facet '{facet_name}' not found in {FACET_DATA_PATH}")
        return None
        
    return facet_entry
