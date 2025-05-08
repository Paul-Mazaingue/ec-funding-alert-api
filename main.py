import time
import logging
from src.fetch import check_new_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
PARAMS = {
    "apiKey": "SEDIA",
    "text": "***"
}

if __name__ == "__main__":
    
    while True:
        try:
            check_new_results(URL, PARAMS)
        except Exception as e:
            logging.exception("Une erreur est survenue lors de la vérification des résultats.")
        logging.info("Attente de 5 minutes avant la prochaine vérification...")
        time.sleep(300)
