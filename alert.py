import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

SENDER = os.getenv("APP_GOOGLE_EMAIL")
PASSWORD = os.getenv("APP_GOOGLE_PASSWORD")
RECEIVER = "p.mazaingue@ideta.be"

def send_email_alert(results: List[Dict[str, str]]) -> None:
    if not results:
        logging.info("No new results to email.")
        return

    msg = MIMEMultipart()
    msg["From"] = SENDER
    msg["To"] = RECEIVER
    msg["Subject"] = "Nouvelle alerte de résultats détectée"

    body = "\n\n".join([f"- {r['title']} ({r['identifier']})\nURL: {r['url']}" for r in results])
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER, PASSWORD)
            server.sendmail(SENDER, RECEIVER, msg.as_string())
        logging.info("Email envoyé avec succès.")
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi de l'e-mail : {e}")
