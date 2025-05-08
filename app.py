import asyncio
import logging
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from src.utils import load_json, save_json
from src.core import periodic_checker

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

CONFIG_PATH = "config/config.json"
ALERTS_PATH = "data/alerts.json"

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(periodic_checker())
    logging.info("Tâche de veille démarrée.")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    config = load_json(CONFIG_PATH) or {"emails": [], "interval": 5}
    alerts = load_json(ALERTS_PATH) or []
    return templates.TemplateResponse("index.html", {"request": request, "config": config, "alerts": alerts})

@app.post("/update-config")
async def update_config(emails: str = Form(...), interval: int = Form(...), alert_message: str = Form(...)):
    email_list = [e.strip() for e in emails.split(",") if e.strip()]
    save_json({"emails": email_list, "interval": interval, "alert_message":alert_message}, CONFIG_PATH)
    return RedirectResponse("/", status_code=303)
