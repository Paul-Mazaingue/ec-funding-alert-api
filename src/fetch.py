import requests
import logging
from typing import List, Dict, Optional
import json

from .utils import load_json, save_json
from .alert import send_email_alert
import asyncio
import aiohttp
from datetime import datetime

CONFIG_DIR = "config"
DATA_FILE = "data/all_references.json"

def build_files() -> List[tuple]:
    return [
        ('query', (f'{CONFIG_DIR}/query.json', open(f'{CONFIG_DIR}/query.json', 'rb'), 'application/json')),
        ('languages', (f'{CONFIG_DIR}/languages.json', open(f'{CONFIG_DIR}/languages.json', 'rb'), 'application/json')),
        ('sort', (f'{CONFIG_DIR}/sort.json', open(f'{CONFIG_DIR}/sort.json', 'rb'), 'application/json'))
    ]

def request_api(url: str, params: Dict) -> Optional[requests.Response]:
    files = build_files()
    try:
        response = requests.post(url, params=params, files=files)
        if response.status_code != 200:
            logging.error(f"API Error {response.status_code}: {response.text}")
            return None
        return response
    except requests.RequestException as e:
        logging.error(f"API request failed: {e}")
        return None
    finally:
        for _, f in files:
            f[1].close()

async def request_api_async(url: str, params: Dict) -> Optional[Dict]:
    files = build_files()
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        for key, (filename, file, content_type) in files:
            data.add_field(key, file, filename=filename, content_type=content_type)
        try:
            async with session.post(url, params=params, data=data) as response:
                if response.status != 200:
                    logging.error(f"API Error {response.status}: {await response.text()}")
                    return None
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"API request failed: {e}")
            return None
        finally:
            for _, f in files:
                f[1].close()

async def fetch_all_references(url: str, params: Dict) -> List[Dict]:
    all_refs = []
    response = await request_api_async(url, params)
    if not response:
        return []

    total_results = response.get("totalResults", 0)
    page_size = 100
    total_pages = (total_results + page_size - 1) // page_size

    async def fetch_page(page: int):
        paged_params = params.copy()
        paged_params.update({"pageNumber": page, "pageSize": page_size})
        resp = await request_api_async(url, paged_params)
        if not resp:
            return []
        print("Page ", page, "/", total_pages)
        if len(resp.get("results", [])) < page_size:
            print(f"Page {page} returned fewer results than expected: {len(resp.get('results', []))} results")
        results = resp.get("results", [])
        return [
            {"reference": result.get("reference"), "identifier": result.get("metadata", {}).get("identifier")}
            for result in results if result.get("reference") and result.get("metadata", {}).get("identifier")
        ]

    # Process pages in batches of 10 to not overwhelm the server
    batch_size = 20
    for i in range(0, total_pages, batch_size):
        tasks = [fetch_page(page) for page in range(i + 1, min(i + batch_size + 1, total_pages + 1))]
        pages = await asyncio.gather(*tasks)
        for page_results in pages:
            all_refs.extend(page_results)
    
    print("Total references fetched: ", len(all_refs))

    return all_refs

def load_previous_results() -> Optional[List[Dict]]:
    return load_json(DATA_FILE)

def compare_results(old: Optional[List[Dict]], new: List[Dict]) -> Dict[str, List[Dict]]:
    if not old:
        return {"new": new, "removed": []}
    
    old_refs = {item["reference"] for item in old}
    new_refs = {item["reference"] for item in new}

    added = [item for item in new if item["reference"] not in old_refs]
    removed = [item for item in old if item["reference"] not in new_refs]

    return {"new": added, "removed": removed}

async def get_detailed_info(identifier: str, reference: str, url: str, params: Dict) -> Optional[Dict]:
    query = load_json(f"{CONFIG_DIR}/query.json")
    if not query:
        logging.error("query.json introuvable.")
        return None

    query.setdefault("bool", {}).setdefault("must", []).append({
        "text": {
            "query": identifier,
            "fields": ["identifier"],
            "defaultOperator": "AND"
        }
    })

    async def open_files():
        return [
            ('query', ('inline-query.json', json.dumps(query), 'application/json')),
            ('languages', ('languages.json', open(f'{CONFIG_DIR}/languages.json', 'rb'), 'application/json')),
            ('sort', ('sort.json', open(f'{CONFIG_DIR}/sort.json', 'rb'), 'application/json'))
        ]

    page = 1
    results = []

    while True:
        params["pageNumber"] = page
        files = await open_files()
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            for key, (filename, file, content_type) in files:
                data.add_field(key, file, filename=filename, content_type=content_type)
            try:
                async with session.post(url, params=params, data=data) as response:
                    if response.status != 200:
                        logging.error(f"Erreur de réponse API : {response.status} - {await response.text()}")
                        return None
                    data = await response.json()
                    results += data.get("results", [])
                    if page * data.get("pageSize", 100) >= data.get("totalResults", 0):
                        break
                    page += 1
            except aiohttp.ClientError as e:
                logging.error(f"API request failed: {e}")
                return None
            finally:
                for _, f in files:
                    if hasattr(f[1], 'close'):
                        f[1].close()

    for res in results:
        if res.get("reference") == reference:
            metadata = res.get("metadata", {})
            call_url = res.get("url", "")
            if call_url.endswith(".json"):
                full_url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier}"
            else:
                callccm2 = metadata.get("callccm2Id", [""])[0]
                full_url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/competitive-calls-cs/{callccm2}"

            def format_date(date_str: str) -> str:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f%z")
                    return date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    return date_str  # Return the original string if parsing fails

            return {
                "title": metadata.get("title"),
                "starting_date": format_date(metadata.get("startDate")[0] if isinstance(metadata.get("startDate"), list) else metadata.get("startDate")),
                "deadline": format_date(metadata.get("deadlineDate")[0] if isinstance(metadata.get("deadlineDate"), list) else metadata.get("deadlineDate")),
                "type": map_type(metadata.get("type")[0]),
                "status": map_status(metadata.get("status")[0]),
                "url": full_url,
                "identifier": identifier,
                "reference": reference
            }
    return None

def map_type(type_code: str) -> str:
    return {
        "0": "Tenders",
        "1": "Direct calls for proposals (issued by the EU)",
        "2": "EU External Actions",
        "6": "Funding",
        "8": "Cascade funding"
    }.get(type_code, "Other")

def map_status(status_code: str) -> str:
    return {
        "31094501": "Open",
        "31094502": "Closed",
        "31094503": "Forthcoming"
    }.get(status_code, "Other")

async def check_new_results(url: str, params: Dict, receivers: List[str]) -> List[Dict]:
    current = await fetch_all_references(url, params)
    previous = load_previous_results()
    comparison = compare_results(previous, current)

    save_json(current, DATA_FILE)

    if comparison["new"]:
        print("Nouveau(x) résultat(s) détecté(s)")
        logging.info(f"{len(comparison['new'])} nouveau(x) résultat(s) détecté(s).")

        details_tasks = [
            get_detailed_info(item["identifier"][0], item["reference"], url, params)
            for item in comparison["new"]
        ]
        details = await asyncio.gather(*details_tasks)
        details = [d for d in details if d]

        if details:
            send_email_alert(details, receivers)
            return details
    else:
        logging.info("✅ Aucun nouveau résultat.")
    return []