import requests
import json
import time
import os

url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***"

payload = {}
files = [
    ('query', ('cs-param.json', open('cs-param.json', 'rb'), 'application/json')),
    ('languages', ('languages.json', open('languages.json', 'rb'), 'application/json'))
]
headers = {}

def load_previous_results():
    if os.path.exists("response.json"):
        with open("response.json", "r", encoding="utf-8") as file:
            return json.load(file)
    return None

def has_new_results(previous_results, current_results):
    if previous_results is None:
        return True  # Si aucun résultat précédent, considérer comme nouveau
    return len(current_results.get("results", [])) > len(previous_results.get("results", []))

# Fonction pour effectuer la requête et vérifier les nouveaux résultats
def check_new_results():
    response = requests.request("POST", url, headers=headers, data=payload, files=files)
    if response.status_code == 200:
        current_results = response.json()
        previous_results = load_previous_results()
        
        if has_new_results(previous_results, current_results):
            print("Nouveaux résultats détectés !")
        else:
            print("Aucun nouveau résultat.")
        
        with open("response.json", "w", encoding="utf-8") as file:
            json.dump(current_results, file, ensure_ascii=False, indent=4)
    else:
        print(f"Error: {response.status_code} - {response.text}")

# Boucle infinie pour vérifier toutes les 5 minutes
while True:
    print("Vérification des nouveaux résultats...")
    check_new_results()
    time.sleep(300)  # Pause de 5 minutes (300 secondes)