import json
import requests
import aiohttp
import asyncio
from typing import List, Dict, Optional
from .utils import load_json, save_json

URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/facet"
PARAMS = {"apiKey": "SEDIA", "text": "***"}
CONFIG_DIR = "config"
DATA_DIR = "data"

def transform_facets(data: Dict, output_file: str):
    output = []

    for facet in data.get('facets', []):
        name = facet.get('name')
        entries = [
            {
                "rawValue": value["rawValue"],
                "value": value["value"]
            }
            for value in facet.get("values", [])
        ]
        output.append({name: entries})

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

def build_files() -> List[tuple]:
    return [
        ('query', (f'{CONFIG_DIR}/facet.json', open(f'{CONFIG_DIR}/facet.json', 'rb'), 'application/json')),
        ('languages', (f'{CONFIG_DIR}/languages.json', open(f'{CONFIG_DIR}/languages.json', 'rb'), 'application/json'))
    ]

async def request_api_async(url: str, params: Dict, retries: int = 3, timeout: int = 30) -> Optional[Dict]:
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    for attempt in range(1, retries + 1):
        files = build_files()  # Rebuild files on each attempt
        data = aiohttp.FormData()
        for key, (filename, file, content_type) in files:
            data.add_field(key, file, filename=filename, content_type=content_type)

        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            try:
                async with session.post(url, params=params, data=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"[{attempt}/{retries}] API Error {response.status}: {error_text[:300]}")
                        await asyncio.sleep(2 * attempt)
                        continue

                    text = await response.text()
                    print(f"[{attempt}/{retries}] Response length: {len(text)} chars")

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        print(f"[{attempt}/{retries}] JSON decode error: {e}")
                        print(f"Truncated response: {text[:500]}")
                        await asyncio.sleep(2 * attempt)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[{attempt}/{retries}] Request failed: {repr(e)}")
                await asyncio.sleep(2 * attempt)
            finally:
                for _, f in files:
                    f[1].close()

    print(f"All {retries} attempts failed for URL: {url}")
    return None

def get_value_from_rawValue(rawValue: str, facet_name: str) -> str:
    facet = load_json(f'{DATA_DIR}/facet.json')
    facet_data = next((item for item in facet if facet_name in item), None)
    if not facet_data:
        print(f"Error: '{facet_name}' not found in facet.json")
        return None
    for item in facet_data[facet_name]:
        if item.get('rawValue') == rawValue:
            return item.get('value')
    return rawValue

def get_rawValue_from_value(value: str, facet_name: str) -> str:
    facet = load_json(f'{DATA_DIR}/facet.json')
    facet_data = next((item for item in facet if facet_name in item), None)
    if not facet_data:
        print(f"Error: '{facet_name}' not found in facet.json")
        return None
    for item in facet_data[facet_name]:
        if item.get('value') == value:
            return item.get('rawValue')
    return value

def get_all_values(facet_name: str) -> List[str]:
    facet = load_json(f'{DATA_DIR}/facet.json')
    facet_data = next((item for item in facet if facet_name in item), None)
    if not facet_data:
        print(f"Error: '{facet_name}' not found in facet.json")
        return []
    return [item.get('value') for item in facet_data[facet_name]]

if __name__ == "__main__":
    print(get_value_from_rawValue("43108390", "frameworkProgramme"))
    print(get_rawValue_from_value("Horizon Europe (HORIZON)", "frameworkProgramme"))
    #loop = asyncio.get_event_loop()
    #result = loop.run_until_complete(request_api_async(URL, PARAMS))
    #if result:
    #    print("API response received successfully.")
    #    # Process the result as needed
    #    # For example, save it to a file or print it
    #    transform_facets(result, DATA_DIR+'/facet.json')
    #else:
    #    print("Failed to get a valid response from the API.")
