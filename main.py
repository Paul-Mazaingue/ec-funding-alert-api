import requests
import json
import os
import time

DATA_DIR = "data"
CONFIG_DIR = "config"

def build_files():
    return [
        ('query', (f'{CONFIG_DIR}/query.json', open(f'{CONFIG_DIR}/query.json', 'rb'), 'application/json')),
        ('languages', (f'{CONFIG_DIR}/languages.json', open(f'{CONFIG_DIR}/languages.json', 'rb'), 'application/json')),
        ('sort', (f'{CONFIG_DIR}/sort.json', open(f'{CONFIG_DIR}/sort.json', 'rb'), 'application/json'))
    ]

def request_api(url, params):
    files = build_files()
    response = requests.post(url, params=params, files=files)
    for _, f in files:
        f[1].close()  # fermer les fichiers pour éviter les fuites
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return None
    return response


def save_to_file(filename, data, folder= None):
    if folder:
        filename = f"{folder}/{filename}"
        if not os.path.exists(folder):
            os.makedirs(folder)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(file_path, folder= None):
    if folder:
        file_path = f"{folder}/{file_path}"
        if not os.path.exists(folder):
            os.makedirs(folder)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    return None


def fetch_all_references(url, params):
    all_refs = []

    totalResults = request_api(url, params).json().get("totalResults", 0)

    page_size = 100
    max_pages = totalResults // page_size + 1 if totalResults % page_size != 0 else totalResults // page_size

    for page in range(1, max_pages + 1):
        print(f"Fetching page {page}/{max_pages}")

        paged_params = params.copy()
        paged_params["pageNumber"] = page
        paged_params["pageSize"] = page_size

        response = request_api(url, paged_params)

        if response is None:
            break

        json_data = response.json()
        results = json_data.get("results", [])

        for result in results:
            ref = result.get("reference")
            identifier = result.get("metadata", {}).get("identifier")
            if ref:
                all_refs.append({"reference": ref, "identifier": identifier})
    
    return all_refs


def load_previous_results(folder= None):
    if folder:
        file_path = f"{folder}/all_references.json"
        if not os.path.exists(folder):
            os.makedirs(folder)
    else:
        file_path = "all_references.json"

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    return None


def has_new_results(previous_results, current_results):
    if previous_results is None:
        return True  # If no previous results, consider as new
    return len(current_results) > len(previous_results)

def compare_results(previous_results, current_results):
    if previous_results is None:
        return {
            "new": current_results,
            "removed": []
        }

    previous_refs = {item["reference"] for item in previous_results}
    current_refs = {item["reference"] for item in current_results}

    new_results = [item for item in current_results if item["reference"] not in previous_refs]
    removed_results = [item for item in previous_results if item["reference"] not in current_refs]

    return {
        "new": new_results,
        "removed": removed_results
    }


def check_new_results(url, params, files):
    current_results = fetch_all_references(url, params)
    previous_results = load_previous_results(folder=DATA_DIR)

    if has_new_results(previous_results, current_results):
        print("New results detected!")
        comparison = compare_results(previous_results, current_results)
        print(f"New results: {comparison['new']}")
        print(f"Removed results: {comparison['removed']}")
    else:
        print("No new results.")

    save_to_file("all_references.json", current_results, folder=DATA_DIR)

def get_info_with_ref(identifier,ref, url, params):
    # Charger le contenu de query.json
    base_query = load_json("query.json", folder=CONFIG_DIR)
    if base_query is None:
        print("Erreur : query.json introuvable.")
        return None

    # Ajouter un bloc à la clause "must"
    if "bool" not in base_query:
        base_query["bool"] = {}

    if "must" not in base_query["bool"]:
        base_query["bool"]["must"] = []

    base_query["bool"]["must"].append({
        "term": {
            "identifier": identifier
        }
    })

    # Ouverture manuelle des fichiers nécessaires
    lang_file = open(f'{CONFIG_DIR}/languages.json', 'rb')
    sort_file = open(f'{CONFIG_DIR}/sort.json', 'rb')

    files = [
        ('query', ('inline-query.json', json.dumps(base_query), 'application/json')),
        ('languages', ('languages.json', lang_file, 'application/json')),
        ('sort', ('sort.json', sort_file, 'application/json'))
    ]

    try:
        response = requests.post(url, params=params, files=files)
    finally:
        lang_file.close()
        sort_file.close()

    if response.status_code != 200:
        print(f"Erreur lors de la récupération : {response.status_code} - {response.text}")
        return None

    data = response.json()
    results = data.get("results", [])
    if not results:
        print(f"Aucun résultat trouvé pour l'identifiant : {identifier}")
        return None

    
    # Il faudra faire en sorte de récupérer le résultat correspondant à la reférence
    result = None
    for res in results:
        print("essai")
        if res.get("reference") == ref:
            print("trouvé")
            result = res
            break


    save_to_file("result.json", result, folder=DATA_DIR)

    return {
        "reference": result.get("reference"),
        "title": result.get("title"),
        "programme": result.get("summary"),
        "startDate": result.get("url")
    }


if __name__ == "__main__":
    
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"

    params = {
        "apiKey": "SEDIA",
        "text": "***"
    }

    files = build_files()

    
    """
    
    while True:
        check_new_results(url, params, files)
        print("Waiting for 5 minutes before the next check...")
        time.sleep(300)  # Wait for 5 minutes (300 seconds)
    """
    
    details = get_info_with_ref("SC5-23-2016-2017","31071371Coordinationandsupportaction1447113600000", url, params)
    if details:
        print("=== Détails de l'appel d'offre ===")
        for k, v in details.items():
            print(f"{k}: {v}")

