import asyncio
import logging
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from src.utils import load_json, save_json
from src.core import periodic_checker
from src.query import generate_query
from src.facet import get_all_values, get_value_from_rawValue, get_rawValue_from_value
from datetime import datetime
from typing import List

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

CONFIG_PATH = "config/config.json"
ALERTS_PATH = "data/alerts.json"
QUERY_PATH = "config/query.json"

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(periodic_checker())
    logging.info("Tâche de veille démarrée.")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    config = load_json(CONFIG_PATH) or {"emails": [], "interval": 5, "keywords": []}
    alerts = load_json(ALERTS_PATH) or []
    raw_query = load_json(QUERY_PATH) or {}

        # Transformation des rawValue en value
    query = {
        "type": [],
        "status": [],
        "frameworkProgramme": [],
        "callIdentifier": [],
        "startDate": {},
        "deadlineDate": {},
        "text_search": ""
    }

    # Parcourir la structure de raw_query pour extraire les termes
    for condition in raw_query.get("bool", {}).get("must", []):

        if "terms" in condition:
            if "type" in condition["terms"]:
                query["type"] = [get_value_from_rawValue(raw, "type") for raw in condition["terms"]["type"]]
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
                

    available_query = {
        "type": get_all_values("type"),
        "status": get_all_values("status"),
        "frameworkProgramme": get_all_values("frameworkProgramme"),
        "callIdentifier": get_all_values("callIdentifier"),
    }

    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": config,
        "alerts": alerts,
        "query": query,
        "available_query": available_query
    })

@app.post("/update-config")
async def update_config(emails: str = Form(...), interval: int = Form(...), alert_message: str = Form(...), keywords: str = Form(...)):
    email_list = [e.strip() for e in emails.split(",") if e.strip()]
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    save_json({"emails": email_list, "interval": interval, "alert_message": alert_message, "keywords": keyword_list}, CONFIG_PATH)
    return RedirectResponse("/", status_code=303)

@app.post("/update-query")
async def update_query(
    type: List[str] = Form(...),
    status: List[str] = Form(...),
    frameworkProgramme: str = Form(None),
    callIdentifier: str = Form(None),
    startDate_start: str = Form(None),
    startDate_end: str = Form(None),
    deadlineDate_start: str = Form(None),
    deadlineDate_end: str = Form(None),
    text_search: str = Form(...)
):
    query = generate_query(
        types=[get_rawValue_from_value(t.strip(), "type") for t in type if t],
        statuses=[get_rawValue_from_value(s.strip(), "status") for s in status if s],
        framework_programmes=get_rawValue_from_value(frameworkProgramme.strip(), "frameworkProgramme") if frameworkProgramme else None,
        call_identifier=get_rawValue_from_value(callIdentifier.strip(), "callIdentifier") if callIdentifier else None,
        starting_date_range={
            "gte": int(datetime.strptime(startDate_start, "%d-%m-%Y").timestamp() * 1000) if startDate_start else None,
            "lte": int(datetime.strptime(startDate_end, "%d-%m-%Y").timestamp() * 1000) if startDate_end else None
        },
        deadline_range={
            "gte": int(datetime.strptime(deadlineDate_start, "%d-%m-%Y").timestamp() * 1000) if deadlineDate_start else None,
            "lte": int(datetime.strptime(deadlineDate_end, "%d-%m-%Y").timestamp() * 1000) if deadlineDate_end else None
        },
        text_search=text_search.strip()
    )

    save_json(query, QUERY_PATH)
    print("Query saved to ", QUERY_PATH)
    return RedirectResponse("/", status_code=303)
