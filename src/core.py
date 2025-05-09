import asyncio
import logging
from datetime import datetime  # Added import
from .fetch import check_new_results
from .utils import load_json, save_json

CONFIG_PATH = "config/config.json"
ALERTS_PATH = "data/alerts.json"

URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
PARAMS = {"apiKey": "SEDIA", "text": "***"}

async def periodic_checker():
    while True:
        
        config = load_json(CONFIG_PATH) or {"emails": [], "interval": 5, "alert_message": ""}
        try:
            alerts = await check_new_results(URL, PARAMS, config.get("emails", []))
            if alerts:
                timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")  # Generate timestamp
                for alert in alerts:
                    alert["retrieved_at"] = timestamp  # Add timestamp to each alert
                history = load_json(ALERTS_PATH) or []
                save_json(alerts + history[:10], ALERTS_PATH)
        except Exception as e:
            logging.exception("Erreur dans la tâche planifiée")
        await asyncio.sleep(config.get("interval", 5) * 60)