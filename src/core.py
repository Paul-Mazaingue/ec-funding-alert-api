import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Tuple

from .fetch import fetch_all_calls, get_detailed_info, get_total_results
from .mail import send_email_alert
from .utils import load_json, save_json
from .facet import request_facet_api
from .clustering import cluster_alert

# Configuration constants
CONFIG_PATH = "config/config.json"
ALERTS_PATH = "config/alerts.json"
DEFAULT_ALERTS_PATH = "config/default_alerts.json"
DATAFOLDER: str = "data"
CONFIGFOLDER: str = "config"
ALERTS_SUBFOLDER = f"{DATAFOLDER}/alerts"

# API constants
EC_API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
EC_API_PARAMS = {"apiKey": "SEDIA", "text": "***"}

# Timing constants
DEFAULT_CHECK_INTERVAL_MINUTES = 60
CHECKER_SLEEP_SECONDS = 60
ERROR_RETRY_SECONDS = 60

# Max number of details to keep
MAX_SAVED_DETAILS = 300

WEEKLY_FACET_FILE = "data/facet.json"
WEEKLY_FACET_API_INTERVAL_SECONDS = 7 * 24 * 60 * 60  # 1 semaine


async def periodic_checker() -> None:
    """
    Continuously check for new results for each alert based on its frequency.
    
    This function:
    - Dynamically picks up new alerts added to the config file
    - Tracks when each alert was last checked
    - Creates necessary directories and files if they don't exist
    - Handles errors gracefully with logging
    """
    # Keep track of the last time each alert was checked
    last_checked: Dict[str, datetime] = {}
    # Keep track of the alerts we know about
    known_alerts: Set[str] = set()
    
    # Create alerts directory if it doesn't exist
    os.makedirs(ALERTS_SUBFOLDER, exist_ok=True)
    
    while True:
        try:
            # check if ALERTS_PATH exists else copy the default one
            if not os.path.exists(ALERTS_PATH):
                logging.info(f"Le fichier {ALERTS_PATH} n'existe pas, on le copie depuis {DEFAULT_ALERTS_PATH}")
                os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
                with open(DEFAULT_ALERTS_PATH, "r", encoding="utf-8") as f:
                    default_alerts = json.load(f)
                save_json(default_alerts, ALERTS_PATH)

            # Load the alerts from the config file
            alerts = load_json(ALERTS_PATH)
            current_time = datetime.now()
            
            for alert in alerts:
                alert_name = alert.get("name", "unnamed")
                interval_minutes = alert.get("interval", DEFAULT_CHECK_INTERVAL_MINUTES)
                
                # Add to known alerts
                known_alerts.add(alert_name)
                
                # Check if it's time to process this alert
                if _should_check_alert(alert_name, current_time, last_checked, interval_minutes):
                    # check if the alert still exists
                    if _check_deleted(alert_name):
                        continue


                    logging.info(f"Checking alert '{alert_name}'")
                    
                    # Ensure query file exists
                    change_query = _ensure_query_file_exists(alert)
                    
                    try:
                        # Update the total results count
                        total_results = await get_total_results(alert)
                        alert["totalResults"] = total_results
                        
                        comparison = await check_new_results(alert)
                        if comparison and change_query:

                            if (_check_deleted(alert_name) or _check_updated(alert_name)):
                                continue

                            details = await _process_new_results(comparison, alert)

                            # check if alert still exists 
                            if (_check_deleted(alert_name)):
                                continue

                            if(details and not _check_updated(alert_name)):
                                # Update and save alert with new details
                                _update_and_save_alert(alerts, alert_name, details)
                                email_subject = f"Nouveaux résultats : {alert_name}"
                                send_email_alert(details, alert.get("message"), alert.get("emails"), email_subject)

                            # Save the updated alert with totalResults
                            _update_alert_total_results(alerts, alert_name, total_results)

                        # Vérifie que tous les détails dans lastDetails ont un champ "cluster"
                        last_details = alert.get("lastDetails", [])
                        all_have_cluster = all("cluster" in d for d in last_details)
                        if not all_have_cluster:  # Exécuter le clustering si au moins un élément n'a pas de cluster
                            logging.info(f"Démarrage du clustering en arrière-plan pour l'alerte '{alert_name}'")
                            size = len(last_details)
                            nb_clusters = min(max(1, size // 10), 10)
                            # Lancer le clustering dans une tâche de fond pour ne pas bloquer le serveur
                            asyncio.create_task(cluster_alert(alert_name, nb_clusters))

                        
                    except Exception as e:
                        logging.error(f"Error checking alert '{alert_name}': {str(e)}", exc_info=True)
                    
                    _check_updated(alert_name)

                    # Update the last checked time
                    last_checked[alert_name] = current_time
            
            # Clean up any alerts that no longer exist
            _cleanup_removed_alerts(last_checked, known_alerts)
            known_alerts.clear()
            
            # Sleep before checking again
            await asyncio.sleep(CHECKER_SLEEP_SECONDS)
        
        except Exception as e:
            logging.error(f"Error in periodic checker: {str(e)}", exc_info=True)
            await asyncio.sleep(ERROR_RETRY_SECONDS)

def _check_updated(alert_name):
    """
    Check if the alert has been updated.
    
    Args:
        alert_name: The name of the alert to check
    
    Returns:
        True if the alert has been updated, False otherwise
    """
    alerts = load_json(ALERTS_PATH)
    if any( a.get("updated") for a in alerts):
        # updated to false
        for i, alert in enumerate(alerts):
            if alert.get("name") == alert_name:
                alerts[i]["updated"] = False
                save_json(alerts, ALERTS_PATH)
                logging.info(f"L'alerte '{alert_name}' a été mise à jour.")
        return True
    return False

def _check_deleted(alert_name):
    """
    Check if the alert has been deleted.
    
    Args:
        alert_name: The name of the alert to check
    
    Returns:
        True if the alert has been deleted, False otherwise
    """
    alerts = load_json(ALERTS_PATH)
    
    if not any(a.get("name") == alert_name for a in alerts):
        logging.info(f"L'alerte '{alert_name}' a été supprimée, on skip la suite.")
        # Check if the files related to the alert are deleted
        if os.path.exists(f"{ALERTS_SUBFOLDER}/{alert_name}.json"):
            os.remove(f"{ALERTS_SUBFOLDER}/{alert_name}.json")
        if os.path.exists(f"{ALERTS_SUBFOLDER}/{alert_name}_query.json"):
            os.remove(f"{ALERTS_SUBFOLDER}/{alert_name}_query.json")
        return True
    return False


def _should_check_alert(
    alert_name: str, 
    current_time: datetime, 
    last_checked: Dict[str, datetime], 
    interval_minutes: int
) -> bool:
    """Determine if an alert should be checked based on its interval."""
    return (alert_name not in last_checked or 
            (current_time - last_checked[alert_name]).total_seconds() >= interval_minutes * 60)


def _ensure_query_file_exists(alert: Dict[str, Any]) -> bool:
    """
    Create the query file if it doesn't exist, or update it if the content differs from alert.
    Returns True if the file exists and is identical to the alert's query, False otherwise.
    """
    file_path = alert.get("file_paths", {}).get("query")
    if file_path:
        query_in_alert = alert.get("query")
        if not os.path.exists(file_path):
            logging.info(f"Query file {file_path} doesn't exist. Creating a new file.")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(query_in_alert, f, indent=4, ensure_ascii=False)
            return False
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    query_in_file = json.load(f)
                if json.dumps(query_in_file, sort_keys=True) != json.dumps(query_in_alert, sort_keys=True):
                    logging.info(f"Query in {file_path} differs from alert. Updating file.")
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(query_in_alert, f, indent=4, ensure_ascii=False)
                    return False
                else:
                    return True
            except Exception as e:
                logging.warning(f"Could not read or parse {file_path}: {e}. Overwriting with alert query.")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(query_in_alert, f, indent=4, ensure_ascii=False)
                return False
    return False


def _update_and_save_alert(alerts: List[Dict[str, Any]], alert_name: str, details: List[Dict[str, Any]]) -> None:
    """Update an alert with new details and save all alerts to config."""
    # Find and update the alert in the list
    for i, alert in enumerate(alerts):
        if alert.get("name") == alert_name:
            alerts[i] = save_details(details, alert)
            break
    
    # Save the updated alerts configuration
    save_json(alerts, ALERTS_PATH)


def _cleanup_removed_alerts(last_checked: Dict[str, datetime], known_alerts: Set[str]) -> None:
    """Remove tracking for alerts that no longer exist."""
    for alert_name in list(last_checked.keys()):
        if alert_name not in known_alerts:
            logging.info(f"Alert '{alert_name}' has been removed, no longer tracking")
            del last_checked[alert_name]
            # delete the alert file if it exists
            file_path = f"{ALERTS_SUBFOLDER}/{alert_name}.json"
            if os.path.exists(file_path):
                os.remove(file_path)
            file_path_query = f"{ALERTS_SUBFOLDER}/{alert_name}_query.json"
            if os.path.exists(file_path_query):
                os.remove(file_path_query)


def save_details(details: List[Dict[str, Any]], alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save details to the alert and add a timestamp.
    
    Args:
        details: The new details to add to the alert
        alert: The alert to update
    
    Returns:
        The updated alert with the new details
    """
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    for detail in details:
        detail["retrieved_at"] = timestamp

    # Limit the number of saved details to avoid large config files
    alert["lastDetails"] = (details + alert.get("lastDetails", []))[:MAX_SAVED_DETAILS]

    return alert


def compare_results(old: Optional[List[Dict[str, Any]]], new: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compare old and new results to find added and removed items.
    
    Args:
        old: List of previous results, may be None
        new: List of current results
    
    Returns:
        Dictionary with "new" and "removed" items
    """
    if not old:
        return {"new": new, "removed": []}
    
    old_refs = {item["reference"] for item in old}
    new_refs = {item["reference"] for item in new}

    added = [item for item in new if item["reference"] not in old_refs]
    removed = [item for item in old if item["reference"] not in new_refs]

    return {"new": added, "removed": removed}


def load_previous_results(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Load previous results for an alert from its JSON file.
    
    Args:
        alert: The alert configuration
    
    Returns:
        List of previous results or empty list if none available
    """
    try:
        file_path = f"{ALERTS_SUBFOLDER}/{alert.get('name')}.json"
        if not os.path.exists(file_path):
            logging.info(f"File {file_path} doesn't exist. No previous results loaded.")
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        logging.warning(f"File {file_path} contains invalid JSON. No previous results loaded.")
        return []
    except Exception as e:
        logging.warning(f"Error loading previous results: {str(e)}")
        return []


async def check_new_results(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check for new results for a given alert.
    
    Args:
        alert: The alert configuration
    
    Returns:
        List of new detailed results if any, otherwise empty list
    """
    current = await fetch_all_calls(alert) 
    previous = load_previous_results(alert)
    comparison = compare_results(previous, current)

    # Vérifier si l'alerte existe toujours après la récupération des résultats
    alerts = load_json(ALERTS_PATH)
    if not any(a.get("name") == alert.get("name") for a in alerts):
        logging.info(f"L'alerte '{alert.get('name')}' a été supprimée pendant la récupération, on skip la suite.")
        # Vérifier que les fichiers liés à l'alerte sont supprimés
        if os.path.exists(f"{ALERTS_SUBFOLDER}/{alert.get('name')}.json"):
            os.remove(f"{ALERTS_SUBFOLDER}/{alert.get('name')}.json")
        if os.path.exists(f"{ALERTS_SUBFOLDER}/{alert.get('name')}.json"):
            os.remove(f"{ALERTS_SUBFOLDER}/{alert.get('name')}_query.json")
        return []
    else:
        file_path = f"{ALERTS_SUBFOLDER}/{alert.get('name')}.json"
        save_json(current, file_path)

    if comparison["new"] and current:
        logging.info(f"{len(comparison['new'])} new result(s) detected.")
        return comparison["new"]
    else:
        logging.info("✅ No new results.")
        return []


async def _process_new_results(new_items: List[Dict[str, Any]], alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Process new results by getting detailed information and sending alerts.
    
    Args:
        new_items: List of new items detected
        alert: The alert configuration
    
    Returns:
        List of detailed information for the new items
    """
    details_tasks = []
    # Limite le nombre de requêtes simultanées avec un sémaphore
    semaphore = asyncio.Semaphore(20)

    async def limited_get_detailed_info(identifier_value, reference, alert):
        async with semaphore:
            return await get_detailed_info(identifier_value, reference, alert)

    for item in new_items:
        identifier_value = item["identifier"][0] if isinstance(item["identifier"], list) else item["identifier"]
        task = limited_get_detailed_info(identifier_value, item["reference"], alert)
        details_tasks.append(task)
    
    details = await asyncio.gather(*details_tasks)
    details = [d for d in details if d]
    
    return details


async def weekly_facet_api_task():
    """
    Exécute request_api_async une fois par semaine pour mettre à jour les facettes.
    """
    while True:
        try:
            await request_facet_api(WEEKLY_FACET_FILE)
            logging.info("Exécution hebdomadaire de request_api_async terminée.")
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution hebdomadaire de request_api_async: {e}", exc_info=True)
        await asyncio.sleep(WEEKLY_FACET_API_INTERVAL_SECONDS)


def _update_alert_total_results(alerts: List[Dict[str, Any]], alert_name: str, total_results: int) -> None:
    """Update an alert with the total results count and save all alerts to config."""
    updated = False
    for i, alert in enumerate(alerts):
        if alert.get("name") == alert_name:
            alerts[i]["totalResults"] = total_results
            updated = True
            break
    
    if updated:
        # Save the updated alerts configuration
        save_json(alerts, ALERTS_PATH)
