import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple, BinaryIO

import aiohttp

# Constants for request configuration
RETRY_DELAY_MULTIPLIER = 2
MAX_ERROR_TEXT_LENGTH = 300
MAX_RESPONSE_PREVIEW_LENGTH = 500
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30

# Type aliases for better readability
FormFile = Tuple[str, Tuple[str, BinaryIO, str]]
FormFilesList = List[FormFile]


def build_files(file_paths: Dict[str, str]) -> FormFilesList:
    """
    Constructs a list of files to send with the request from the provided paths.
    
    Args:
        file_paths: Dictionary mapping field names to file paths
        
    Returns:
        List of tuples containing file info for FormData
        
    Raises:
        FileNotFoundError: If a required file cannot be found
    """
    files = []
    for key, path in file_paths.items():
        try:
            file = open(path, 'rb')
            files.append((key, (path, file, 'application/json')))
        except FileNotFoundError:
            error_msg = f"Error: File {path} not found."
            print(error_msg)
            raise FileNotFoundError(error_msg)
    return files


def create_form_data(files: FormFilesList) -> aiohttp.FormData:
    """
    Creates a FormData object from the provided files.
    
    Args:
        files: List of file tuples to add to the form
        
    Returns:
        FormData object with all files added
    """
    data = aiohttp.FormData()
    for key, (filename, file, content_type) in files:
        data.add_field(key, file, filename=filename, content_type=content_type)
    return data


async def handle_response(response: aiohttp.ClientResponse, attempt: int, retries: int) -> Optional[Dict[str, Any]]:
    """
    Handles the API response.
    
    Args:
        response: Response from the API call
        attempt: Current attempt number
        retries: Maximum number of retry attempts
        
    Returns:
        Parsed JSON response or None if an error occurred
    """
    if response.status != 200:
        error_text = await response.text()
        print(f"[{attempt}/{retries}] API Error {response.status}: {error_text[:MAX_ERROR_TEXT_LENGTH]}")
        return None

    text = await response.text()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[{attempt}/{retries}] JSON decode error: {e}")
        print(f"Truncated response: {text[:MAX_RESPONSE_PREVIEW_LENGTH]}")
        return None


async def make_request(
    session: aiohttp.ClientSession, 
    url: str, 
    params: Dict[str, Any], 
    data: aiohttp.FormData, 
    attempt: int, 
    retries: int
) -> Optional[Dict[str, Any]]:
    """
    Performs a POST request and handles the response.
    
    Args:
        session: aiohttp client session
        url: URL to send the request to
        params: URL parameters to include
        data: FormData to send in the request body
        attempt: Current attempt number
        retries: Maximum number of retry attempts
        
    Returns:
        Parsed JSON response or None if an error occurred
    """
    try:
        async with session.post(url, params=params, data=data) as response:
            return await handle_response(response, attempt, retries)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"[{attempt}/{retries}] Request failed: {repr(e)}")
        return None


async def request_api_async(
    url: str, 
    params: Dict[str, Any], 
    file_paths: Dict[str, str], 
    retries: int = DEFAULT_RETRIES, 
    timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> Optional[Dict[str, Any]]:
    """
    Performs an asynchronous POST request with retry handling.
    
    Args:
        url: URL to send the request to
        params: URL parameters to include
        file_paths: Dictionary mapping field names to file paths
        retries: Maximum number of retry attempts
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON response or None if all attempts failed
    """
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    # Ensure directories exist for any file paths we might write to
    for path in file_paths.values():
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    for attempt in range(1, retries + 1):
        files = []
        try:
            files = build_files(file_paths)
            data = create_form_data(files)

            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                result = await make_request(session, url, params, data, attempt, retries)
                if result is not None:
                    return result
                
                # Exponential backoff for retries
                await asyncio.sleep(RETRY_DELAY_MULTIPLIER * attempt)
                
        except Exception as e:
            print(f"[{attempt}/{retries}] Exception during request: {repr(e)}")
        finally:
            # Ensure all files are properly closed
            for _, (_, file, _) in files:
                try:
                    file.close()
                except Exception:
                    pass

    print(f"All {retries} attempts failed for URL: {url}")
    return None



