import requests
import logging
import os
from typing import List, Dict, Optional
import json

from utils import load_json, save_json
from alert import send_email_alert

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

def fetch_all_references(url: str, params: Dict) -> List[Dict]:
    all_refs = []
    response = request_api(url, params)
    if not response:
        return []

    json_data = response.json()
    total_results = json_data.get("totalResults", 0)
    page_size = 100
    total_pages = (total_results + page_size - 1) // page_size

    for page in range(1, total_pages + 1):
        logging.info(f"Fetching page {page}/{total_pages}")
        paged_params = params.copy()
        paged_params.update({"pageNumber": page, "pageSize": page_size})
        resp = request_api(url, paged_params)
        if not resp:
            break
        results = resp.json().get("results", [])
        for result in results:
            ref = result.get("reference")
            identifier = result.get("metadata", {}).get("identifier")
            if ref and identifier:
                all_refs.append({"reference": ref, "identifier": identifier})
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

def get_detailed_info(identifier: str, reference: str, url: str, params: Dict) -> Optional[Dict]:

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

    def open_files():
        return [
            ('query', ('inline-query.json', json.dumps(query), 'application/json')),
            ('languages', ('languages.json', open(f'{CONFIG_DIR}/languages.json', 'rb'), 'application/json')),
            ('sort', ('sort.json', open(f'{CONFIG_DIR}/sort.json', 'rb'), 'application/json'))
        ]

    page = 1
    results = []

    while True:
        params["pageNumber"] = page
        files = open_files()
        try:
            response = requests.post(url, params=params, files=files)
            if response.status_code != 200:
                logging.error(f"Erreur de réponse API : {response.status_code} - {response.text}")
                return None
            data = response.json()
            results += data.get("results", [])
            if page * data.get("pageSize", 100) >= data.get("totalResults", 0):
                break
            page += 1
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

            return {
                "title": metadata.get("title"),
                "starting_date": metadata.get("startDate"),
                "deadline": metadata.get("deadlineDate"),
                "type": map_type(res.get("type")),
                "status": map_status(res.get("status")),
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

def check_new_results(url: str, params: Dict) -> None:
    current = fetch_all_references(url, params)
    previous = load_previous_results()
    comparison = compare_results(previous, current)

    if comparison["new"]:
        logging.info(f"{len(comparison['new'])} nouveau(x) résultat(s) détecté(s).")
        details = [
            get_detailed_info(item["identifier"][0], item["reference"], url, params)
            for item in comparison["new"]
        ]
        details = [d for d in details if d]
        send_email_alert(details)
    else:
        logging.info("Aucun nouveau résultat.")

    save_json(current, DATA_FILE)
