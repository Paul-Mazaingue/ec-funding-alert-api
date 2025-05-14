import json
import logging
import os
from typing import Any, Optional

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_json(file_path: str) -> Optional[Any]:
    """
    Load JSON data from a file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        Parsed JSON data or None if loading failed
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"File {file_path} does not exist.")
            return None
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in file {file_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}", exc_info=True)
        return None


def save_json(data: Any, file_path: str) -> bool:
    """
    Save data as JSON to a file.
    
    Args:
        data: Data to save as JSON
        file_path: Path to save the file
        
    Returns:
        True if save was successful, False otherwise
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        # Write the file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # Verify the file was created properly
        if not _verify_json_file(file_path):
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error saving file {file_path}: {e}", exc_info=True)
        return False


def delete_json(file_path: str) -> bool:
    """
    Delete a JSON file.
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        True if deletion was successful or file didn't exist, False on error
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File {file_path} successfully deleted.")
            return True
        else:
            logger.warning(f"File {file_path} does not exist, nothing to delete.")
            return True  # Return True as the end state is as expected - file doesn't exist
            
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}", exc_info=True)
        return False


def _verify_json_file(file_path: str) -> bool:
    """
    Verify a JSON file exists and contains valid data.
    
    Args:
        file_path: Path to the file to verify
        
    Returns:
        True if file exists and contains valid JSON, False otherwise
    """
    if not os.path.exists(file_path):
        logger.error(f"File {file_path} was not created successfully")
        return False
        
    # Check file size to ensure it contains data
    if os.path.getsize(file_path) == 0:
        logger.error(f"File {file_path} was created but is empty")
        return False
        
    # Try to read the file back to verify it's valid JSON
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except json.JSONDecodeError:
        logger.error(f"File {file_path} contains invalid JSON")
        return False
    except Exception as e:
        logger.error(f"Error verifying file {file_path}: {e}")
        return False