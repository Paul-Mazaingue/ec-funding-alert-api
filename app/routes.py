from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from src.facet import get_all_values, get_value_from_rawValue,get_rawValue_from_value
from src.fetch import get_total_results
from src.utils import load_json, save_json
from src.query import generate_query
from datetime import datetime
from typing import Optional, List, Dict
import os
import logging  
import json

TYPE_MAPPINGS: Dict[str, str] = {
    "1": "Direct calls for proposals (issued by the EU)",
    "2": "EU External Actions",
    "8": "Calls for funding in cascade (issued by funded projects)"
}

ALERTS_PATH = "config/alerts.json"
DATA_FOLDER = "data"

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, alert: Optional[str] = None):
    # Load all alerts for sidebar
    all_alerts = load_json(ALERTS_PATH)
    
    # Use selected alert or default
    if alert:
        current_alert_name = alert
    elif all_alerts:
        current_alert_name = all_alerts[0].get("name", "default")
    else:
        current_alert_name = "default"
    alert_config, available_query = load_config(current_alert_name)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "alert": alert_config,
        "available_query": available_query,
        "alerts": all_alerts,
        "current_alert": current_alert_name
    })

@router.get("/delete-alert", response_class=RedirectResponse)
async def delete_alert(name: str):
    alerts = load_json(ALERTS_PATH)
    
    # Filter out the alert to delete
    updated_alerts = [a for a in alerts if a.get("name") != name]
    
    # Don't delete if it's the last alert
    if len(updated_alerts) > 0:
        save_json(updated_alerts, ALERTS_PATH)

    # delete alert file if exists
    alert_file_path = f"{DATA_FOLDER}/alerts/{name}.json"
    alert_query_file_path = f"{DATA_FOLDER}/alerts/{name}_query.json"

    # Delete files with error handling
    for file_path in [alert_file_path, alert_query_file_path]:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Successfully deleted {file_path}")
        except PermissionError:
            logging.warning(f"Cannot delete {file_path} - file is being used by another process")
        except Exception as e:
            logging.error(f"Error deleting {file_path}: {str(e)}")
    
    return RedirectResponse("/", status_code=303)

@router.post("/create-alert", response_class=RedirectResponse)
async def create_alert(new_alert_name: str = Form(...)):
    alerts = load_json(ALERTS_PATH)
    # Check if name already exists
    if not any(a.get("name") == new_alert_name for a in alerts):
        # Create new alert with default values
        new_alert = {
            "name": new_alert_name,
            "interval": 60,
            "emails": [],
            "file_paths": {
                "query": f"data/alerts/{new_alert_name}_query.json",
                "languages": "config/languages.json",
                "sort": "config/sort.json"
            },
            "message": "<strong>{title}</strong>\r\n{summary}\r\n\r\nStarting date : <em>{starting_date}</em>\r\nDeadline: <em>{deadline}</em>\r\n\r\nType : {type}\r\nStatus: {status}\r\n\r\nFramework programme : {frameworkProgramme}\r\n\r\nMore information : {url}",
            "keywords": [],
            "query": {"bool": {"must": [{"terms": {"type": ["1","8","2"]}},{"terms": {"status": ["31094503","31094502","31094501"]}}]}},
            "lastDetails": [],
            "totalResults": 0
        }

        total_results = await get_total_results(new_alert)
        # delete query file if exists
        alert_file_path = f"{DATA_FOLDER}/alerts/{new_alert_name}.json"
        alert_query_file_path = f"{DATA_FOLDER}/alerts/{new_alert_name}_query.json"
        try:
            if os.path.exists(alert_file_path):
                os.remove(alert_file_path)
        except PermissionError:
            logging.warning(f"Cannot delete {alert_file_path} - file is being used by another process")
        except Exception as e:
            logging.error(f"Error deleting {alert_file_path}: {str(e)}")
        try:
            if os.path.exists(alert_query_file_path):
                os.remove(alert_query_file_path)
        except PermissionError:
            logging.warning(f"Cannot delete {alert_query_file_path} - file is being used by another process")
        except Exception as e:
            logging.error(f"Error deleting {alert_query_file_path}: {str(e)}")
        
        new_alert["totalResults"] = total_results
        alerts.append(new_alert)
        save_json(alerts, ALERTS_PATH)

    return RedirectResponse(f"/?alert={new_alert_name}", status_code=303)

@router.post("/update-alert", response_class=RedirectResponse)
async def update_alert(
    request: Request, 
    emails: str = Form(...), 
    interval: int = Form(...), 
    message: str = Form(...),
    keywords: str = Form(...),
    type: List[str] = Form(default=[]),  
    status: List[str] = Form(default=[]), 
    frameworkProgramme: str = Form(None),
    callIdentifier: str = Form(None),
    startDate_start: str = Form(None),
    startDate_end: str = Form(None),
    deadlineDate_start: str = Form(None),
    deadlineDate_end: str = Form(None),
    text_search: str = Form(...),
    alert_name: str = Form(...)  # Récupérer le nom de l'alerte depuis le formulaire
):  
    # Utiliser le nom de l'alerte récupéré du formulaire
    current_alert_name = alert_name
    alerts = load_json(ALERTS_PATH)
    
    # Helper to parse dates with different formats
    def parse_date(date_str):
        if not date_str:
            return None
            
        date_str = date_str.strip()
        if not date_str:
            return None
            
        # Try different date formats
        formats = ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']
        
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                timestamp = int(date_obj.timestamp() * 1000)
                return timestamp
            except ValueError:
                continue
                
        logging.warning(f"Could not parse date: {date_str}")
        return None

    # Process date ranges safely
    start_date_range = {}
    if startDate_start:
        start_gte = parse_date(startDate_start)
        if start_gte:
            start_date_range["gte"] = start_gte
            
    if startDate_end:
        start_lte = parse_date(startDate_end)
        if start_lte:
            start_date_range["lte"] = start_lte
    
    deadline_range = {}
    if deadlineDate_start:
        deadline_gte = parse_date(deadlineDate_start)
        if deadline_gte:
            deadline_range["gte"] = deadline_gte
            
    if deadlineDate_end:
        deadline_lte = parse_date(deadlineDate_end)
        if deadline_lte:
            deadline_range["lte"] = deadline_lte

    mapped_types = [k for t in type for k, v in TYPE_MAPPINGS.items() if v == t.strip()]
    query = generate_query(
        types=mapped_types,
        statuses=[get_rawValue_from_value(s.strip(), "status") for s in status if s],
        framework_programmes=get_rawValue_from_value(frameworkProgramme.strip(), "frameworkProgramme") if frameworkProgramme else None,
        call_identifier=get_rawValue_from_value(callIdentifier.strip(), "callIdentifier") if callIdentifier else None,
        starting_date_range=start_date_range,
        deadline_range=deadline_range,
        text_search=text_search.strip()
    )
    
    for alert in alerts:
        if alert.get("name") == current_alert_name:
            # Reset lastDetails if query or keywords changed
            # Convertir les dictionnaires en JSON pour comparer leur contenu
            if json.dumps(alert.get("query", {}), sort_keys=True) != json.dumps(query, sort_keys=True) or \
               alert.get("keywords") != [k.strip() for k in keywords.split(",") if k.strip()]:
                alert["lastDetails"] = []
            alert["emails"] = [e.strip() for e in emails.split(",") if e.strip()]
            alert["interval"] = interval
            alert["message"] = message
            alert["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
            alert["query"] = query

            total_results = await get_total_results(alert)
            # delete query file if exists
            alert_file_path = f"{DATA_FOLDER}/alerts/{current_alert_name}.json"
            try:
                if os.path.exists(alert_file_path):
                    os.remove(alert_file_path)
            except PermissionError:
                logging.warning(f"Cannot delete {alert_file_path} - file is being used by another process")
            except Exception as e:
                logging.error(f"Error deleting {alert_file_path}: {str(e)}")
            alert_query_file_path = f"{DATA_FOLDER}/alerts/{current_alert_name}_query.json"
            try:
                if os.path.exists(alert_query_file_path):
                    os.remove(alert_query_file_path)
            except PermissionError:
                logging.warning(f"Cannot delete {alert_query_file_path} - file is being used by another process")
            except Exception as e:
                logging.error(f"Error deleting {alert_query_file_path}: {str(e)}")
            
            alert["totalResults"] = total_results
            break
    
    save_json(alerts, ALERTS_PATH)
    return RedirectResponse(f"/?alert={current_alert_name}", status_code=303)

def load_config(alert_name):
    alerts = load_json(ALERTS_PATH)
    alert = next((a for a in alerts if a.get("name") == alert_name), None)
    
    # If alert not found, use the first one or create default
    if not alert:
        if alerts:
            alert = alerts[0]
        else:
            alert = {
                "name": "default",
                "interval": 60,
                "emails": [],
                "message": "",
                "keywords": [],
                "query": {},
                "lastDetails": [],
                "totalResults": 0,
            }

    name = alert.get("name")
    interval = alert.get("interval", 60)
    emails = alert.get("emails", [])
    message = alert.get("message", "")
    keywords = alert.get("keywords", [])
    query = transform_query(alert.get("query", {}))
    details = alert.get("lastDetails", [])
    total_results = alert.get("totalResults", 0)
    available_query = {
        "type": ["Direct calls for proposals (issued by the EU)", "EU External Actions", "Calls for funding in cascade (issued by funded projects)"],
        "status": get_all_values("status"),
        "frameworkProgramme": get_all_values("frameworkProgramme"),
        "callIdentifier": get_all_values("callIdentifier"),
    }

    return {
        "name": name,
        "interval": interval,
        "emails": emails,
        "message": message,
        "keywords": keywords,
        "query": query,
        "details": details,
        "totalResults": total_results
    }, available_query

def transform_query(raw_query):
    query = {
        "type": [],
        "status": [],
        "frameworkProgramme": [],
        "callIdentifier": [],
        "startDate": {},
        "deadlineDate": {},
        "text_search": ""
    }

    for condition in raw_query.get("bool", {}).get("must", []):
        if "terms" in condition:
            if "type" in condition["terms"]:
                query["type"] = [TYPE_MAPPINGS.get(raw, raw) for raw in condition["terms"]["type"]]
            if "status" in condition["terms"]:
                query["status"] = [get_value_from_rawValue(raw, "status") for raw in condition["terms"]["status"]]
        if "text" in condition:
            if "fields" in condition.get("text"):
                argument = condition.get("text")
                fields = argument.get("fields")[0]
                query[fields] = get_value_from_rawValue(argument.get("query"), fields)
        if "range" in condition:
            if "startDate" in condition["range"]:
                start_date_str = condition["range"]["startDate"].get("gte")
                if start_date_str:
                    date_obj = datetime.fromtimestamp(int(start_date_str) / 1000)
                    # Format date as dd-mm-yyyy
                    query["startDate"]["start"] = date_obj.strftime("%d-%m-%Y")
                end_date_str = condition["range"]["startDate"].get("lte")
                if end_date_str:
                    date_obj = datetime.fromtimestamp(int(end_date_str) / 1000)
                    query["startDate"]["end"] = date_obj.strftime("%d-%m-%Y")

            if "deadlineDate" in condition["range"]:
                start_date_str = condition["range"]["deadlineDate"].get("gte")
                if start_date_str:
                    date_obj = datetime.fromtimestamp(int(start_date_str) / 1000)
                    query["deadlineDate"]["start"] = date_obj.strftime("%d-%m-%Y")
                end_date_str = condition["range"]["deadlineDate"].get("lte")
                if end_date_str:
                    date_obj = datetime.fromtimestamp(int(end_date_str) / 1000)
                    query["deadlineDate"]["end"] = date_obj.strftime("%d-%m-%Y")
        if "bool" in condition:
            query["text_search"] = condition["bool"].get("should", [{}])[0].get("phrase", {}).get("query", "")
                
    return query