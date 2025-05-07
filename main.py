import requests
import json
import os
import time

# Sending email alerts
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv


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
        send_alert(comparison["new"], url, params)


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
        "text": {
            "query": identifier[0],
            "fields": ["identifier"],
            "defaultOperator": "AND"
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

    print("========= test ===========")
    print(results)

    # Si le nombre total de résultats est supérieur à la taille de la page multipliée par le numéro de la page, il faut continuer à paginer
    while data.get("totalResults") > data.get("pageSize") * data.get("pageNumber"):
        print("Ajout de la page suivante :" + str(data.get("pageNumber") + 1))
        params["pageNumber"] = data.get("pageNumber") + 1

        # Rebuild the files to ensure they are not closed
        lang_file = open(f'{CONFIG_DIR}/languages.json', 'rb')
        sort_file = open(f'{CONFIG_DIR}/sort.json', 'rb')
        files = [
            ('query', ('inline-query.json', json.dumps(base_query), 'application/json')),
            ('languages', ('languages.json', lang_file, 'application/json')),
            ('sort', ('sort.json', sort_file, 'application/json'))
        ]

        try:
            response = requests.post(url, params=params, files=files)
            data = response.json()
            results.extend(response.json().get("results", []))
        finally:
            lang_file.close()
            sort_file.close()

    result = None
    for res in results:
        if res.get("reference") == ref:
            result = res
            break

    if result is None:
        print(f"No matching result found for reference: {ref}")
        return None

    url_basic = result.get("url")
    if url_basic.endswith(".json"):
        url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/" + identifier[0]
    else:
        url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/competitive-calls-cs/" + result.get("metadata", {}).get("callccm2Id")[0]

    metadata = result.get("metadata", {})
    
    title = metadata.get("title")
    starting_date = metadata.get("startDate")
    deadline = metadata.get("deadlineDate")
    match result.get("type"):
        case "0":
            type = "Tenders"
        case "1":
            type = "Direct calls for proposals (issued by the EU)"
        case "2":
            type = "EU External Actions"
        case "6":
            type = "Funding"
        case "8":
            type = "Calls for funding in cascade (issued by funded projects)"
        case _:
            type = "other" 

    match result.get("status"):
        case "31094501":
            status = "Open"
        case "31094502":
            status = "Closed"
        case "31094503":
            status = "Forthcoming"
        case _:
            status = "other"
    


    return {
        "title": title,
        "starting_date": starting_date,
        "deadline": deadline,
        "type": type,
        "status": status,
        "url": url,
        "identifier": identifier[0],
        "reference": ref,
    }

def send_alert(new_results, url, params):
    # Récupération des informations sur les résultats
    new_info = [get_info_with_ref(item["identifier"], item["reference"], url, params) for item in new_results]
    send_email_alert(new_info)
    
def send_email_alert(new_info):
    sender_email = os.getenv("APP_GOOGLE_EMAIL")
    receiver_email = "p.mazaingue@ideta.be"
    password = os.getenv("APP_GOOGLE_PASSWORD") 

    subject = "Nouvelle alerte de résultats détectée"
    body = json.dumps(new_info, indent=2)

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("Email envoyé avec succès.")
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'e-mail : {e}")


if __name__ == "__main__":
    
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"

    params = {
        "apiKey": "SEDIA",
        "text": "***"
    }

    files = build_files()

    
    # Load environment variables from .env file
    load_dotenv()
    
    
        
    
    while True:
        check_new_results(url, params, files)
        print("Waiting for 5 minutes before the next check...")
        time.sleep(300)  # Wait for 5 minutes (300 seconds)
    """
    details = get_info_with_ref(["SMP-COSME-2021-CLUSTER-01"],"3884COMPETITIVE_CALLen", url, params)
    if details:
        send_email_alert(details)
    """

