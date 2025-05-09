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
                        logging.error(f"[{attempt}/{retries}] API Error {response.status}: {error_text[:300]}")
                        await asyncio.sleep(2 * attempt)
                        continue

                    text = await response.text()
                    logging.info(f"[{attempt}/{retries}] Response length: {len(text)} chars")

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        logging.warning(f"[{attempt}/{retries}] JSON decode error: {e}")
                        logging.debug(f"Truncated response: {text[:500]}")
                        await asyncio.sleep(2 * attempt)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logging.error(f"[{attempt}/{retries}] Request failed: {repr(e)}")
                await asyncio.sleep(2 * attempt)
            finally:
                for _, f in files:
                    f[1].close()

    logging.error(f"All {retries} attempts failed for URL: {url}")
    return None


async def fetch_all_references(url: str, params: Dict) -> List[Dict]:
    all_refs = []
    response = await request_api_async(url, params)
    if not response:
        return []

    total_results = response.get("totalResults", 0)
    page_size = 100
    total_pages = (total_results + page_size - 1) // page_size

    semaphore = asyncio.Semaphore(5)  # Limite à 3 requêtes simultanées

    async def fetch_page(page: int):
        async with semaphore:
            paged_params = params.copy()
            paged_params.update({"pageNumber": page, "pageSize": page_size})
            resp = await request_api_async(url, paged_params)
            if not resp:
                print(f"[ERROR] Page {page} failed.")
                return []
            print("Page ", page, "/", total_pages)
            results = resp.get("results", [])
            if len(results) < page_size:
                print(f"[WARNING] Page {page} returned fewer results than expected: {len(results)} results")
            return [
                {"reference": result.get("reference"), "identifier": result.get("metadata", {}).get("identifier")}
                for result in results if result.get("reference") and result.get("metadata", {}).get("identifier")
            ]

    # Process pages in batches of 20
    batch_size = 20
    for i in range(0, total_pages, batch_size):
        tasks = [fetch_page(page) for page in range(i + 1, min(i + batch_size + 1, total_pages + 1))]
        pages = await asyncio.gather(*tasks)
        for page_results in pages:
            all_refs.extend(page_results)
        await asyncio.sleep(1)  # Pause pour ne pas saturer l'API

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
                    try:
                        text = await response.text()
                        data = json.loads(text)
                    except json.JSONDecodeError as e:
                        text = await response.text()
                        print(f"Response length: {len(text)} chars")
                        print(f"JSON decode error: {e}. Raw response (truncated): {text[:500]}")
                        data = {}
                    results += data.get("results", [])
                    if page * data.get("pageSize", 50) >= data.get("totalResults", 0):
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
                "frameworkProgramme": map_frameworkProgramme(metadata.get("frameworkProgramme")[0]),
                "url": full_url,
                "identifier": identifier,
                "reference": reference,
                "summary": res.get("summary")
            }
    return None

def map_frameworkProgramme(frameworkProgramme_code: str) -> str:
    return {
        "31045243": "Horizon 2020 Framework Programme (H2020 - 2014-2020)",
        "43108390": "Horizon Europe (HORIZON)",
        "43251567": "Connecting Europe Facility (CEF)",
        "43152860": "Digital Europe Programme (DIGITAL)",
        "43353764": "Erasmus+ (ERASMUS+)",
        "43252476": "Single Market Programme (SMP)",
        "44181033": "European Defence Fund (EDF)",
        "43252405": "Programme for the Environment and Climate Action (LIFE)",
        "43251814": "Creative Europe Programme (CREA)",
        "31059643": "Programme for the Competitiveness of Enterprises and small and medium-sized enterprises (COSME - 2014-2020)",
        "43298664": "Promotion of Agricultural Products (AGRIP)",
        "43332642": "EU4Health Programme (EU4H)",
        "43251589": "Citizens, Equality, Rights and Values Programme (CERV)",
        "42810547": "Europe Direct (ED)",
        "31072773": "Promotion of Agricultural Products (AGRIP - 2014-2020)",
        "31076817": "Rights, Equality and Citizenship Programme (REC - 2014-2020)",
        "31061266": "3rd Health Programme (3HP - 2014-2020)",
        "31077817": "Internal Security Fund Police (ISFP - 2014-2020)",
        "43298916": "Euratom Research and Training Programme (EURATOM)",
        "31084392": "Hercule III (HERC - 2014-2020)",
        "31109727": "European Defence Industrial Development Programme (EDIDP - 2014-2020)",
        "43251842": "Union Anti-fraud Programme (EUAF)",
        "111111": "EU External Action - Prospect (RELEX-PROSPECT)",
        "31070247": "Justice Programme (JUST - 2014-2020)",
        "45532249": "EU Bodies and Agencies (EUBA)",
        "43254019": "European Social Fund + (ESF)",
        "43252449": "Research Fund for Coal & Steel (RFCS)",
        "43697167": "European Parliament (EP)",
        "31077795": "Asylum, Migration and Integration Fund (AMIF - 2014-2020)",
        "44416173": "Interregional Innovation Investments Instrument (I3)",
        "31084250": "Pilot Projects and Preparatory Actions (PPPA - 2014-2020)",
        "43089234": "Innovation Fund (INNOVFUND)",
        "43637601": "Pilot Projects & Preparation Actions (PPPA)",
        "31059093": "Erasmus+ Programme (EPLUS - 2014-2020)",
        "31059083": "Creative Europe (CREA - 2014-2020)",
        "43392145": "European Maritime, Fisheries and Aquaculture Fund (EMFAF)",
        "43252368": "Internal Security Fund (ISF)",
        "43252386": "Justice Programme (JUST)",
        "43298203": "Union Civil Protection Mechanism (UCPM)",
        "43252517": "Social Prerogative and Specific Competencies Lines (SOCPL)",
        "31061225": "Research Fund for Coal & Steel (RFCS - 2014-2020)",
        "43251447": "Asylum, Migration and Integration Fund (AMIF)",
        "31061273": "Consumer Programme (CP - 2014-2020)",
        "31082527": "Union Civil Protection Mechanism (UCPM - 2014-2020)",
        "31098847": "European Maritime and Fisheries Fund (EMFF - 2014-2020)",
        "43254037": "European Solidarity Corps (ESC)",
        "31107710": "Programme for the Environment and Climate Action (LIFE - 2014-2020)",
        "43252433": "Programme for the Protection of the Euro against Counterfeiting (PERICLES IV)",
        "31059088": "Europe For Citizens (EFC - 2014-2020)",
        "43251882": "Support for information measures relating to the common agricultural policy (IMCAP)",
        "31077833": "Internal Security Fund Borders and Visa (ISFB - 2014-2020)",
        "43251530": "Border Management and Visa Policy Instrument (BMVI)",
        "44773133": "Information Measures for the EU Cohesion policy (IMREG)",
        "31088049": "European Statistics (ESTAT - 2014-2020)",
        "42198993": "Support for information measures relating to the common agricultural policy (IMCAP - 2014-2020)",
        "43253967": "Renewable Energy Financing Mechanism (RENEWFM)",
        "44773066": "Just Transition Mechanism (JTM)",
        "45876777": "Neighbourhood, Development and International Cooperation Instrument Global Europe (NDICI)",
        "46324255": "Technical assistance for ERDF, CF and JTF (ERDF-TA)",
        "31059098": "EU Aid Volunteers programme (EUAID - 2014-2020)",
        "31075571": "Intra-Africa Academic Mobility Scheme (PANAF - 2014-2020)",
        "42992790": "European Solidarity Corps (ESC - 2014-2020)",
    }.get(frameworkProgramme_code, "Unknown")


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