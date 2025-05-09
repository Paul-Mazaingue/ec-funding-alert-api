import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from dotenv import load_dotenv
from .utils import load_json

load_dotenv()

SENDER = os.getenv("APP_GOOGLE_EMAIL")
PASSWORD = os.getenv("APP_GOOGLE_PASSWORD")
CONFIG_PATH = "config/config.json"
SUBJECT = "Nouvelle alerte de résultats détectée"

def send_email_alert(results: List[Dict[str, str]], receivers: List[str]) -> None:
    if not results or not receivers:
        logging.info("Aucun résultat ou destinataire.")
        return
    
    config = load_json(CONFIG_PATH) or {"emails": [], "interval": 5, "alert_message": ""}


    msg = MIMEMultipart()
    msg["From"] = SENDER
    msg["To"] = ", ".join(receivers)
    msg["Subject"] = SUBJECT

    body = ""
    for result in results:
        alert_message = config["alert_message"]
        title = result.get("title", "")
        if isinstance(title, list):
            title = ", ".join(title)
        alert_message = alert_message.replace("{title}", title)
        alert_message = alert_message.replace("{starting_date}", str(result.get("starting_date", "")))
        alert_message = alert_message.replace("{deadline}", str(result.get("deadline", "")))
        alert_message = alert_message.replace("{type}", str(result.get("type", "")))
        alert_message = alert_message.replace("{status}", str(result.get("status", "")))
        alert_message = alert_message.replace("{url}", str(result.get("url", "")))
        alert_message = alert_message.replace("{identifier}", str(result.get("identifier", "")))
        alert_message = alert_message.replace("{reference}", str(result.get("reference", "")))
        alert_message = alert_message.replace("{summary}", str(result.get("summary", "")))
        alert_message = alert_message.replace("{frameworkProgramme}", str(result.get("frameworkProgramme", "")))
        alert_message = alert_message.replace("\n", "<br>")
        body += (
            f"<div style='border-top: 1px solid #ccc; margin: 20px 0; padding-top: 10px;'>"
            f"{alert_message}"
            f"</div>"
        )

    msg.attach(MIMEText(body, 'html'))  # Change MIME type to 'html'

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER, PASSWORD)
            server.sendmail(SENDER, receivers, msg.as_string())
        print("E-mail envoyé avec succès.")
        logging.info("Email envoyé avec succès.")
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de l'e-mail : {e}")