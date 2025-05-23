import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

from .utils import load_json

# Load environment variables
load_dotenv()

# Email configuration constants
SENDER: Optional[str] = os.getenv("APP_GOOGLE_EMAIL")
PASSWORD: Optional[str] = os.getenv("APP_GOOGLE_PASSWORD")
CONFIG_PATH: str = "config/config.json"
SUBJECT: str = "Nouvelle alerte de résultats détectée"
SMTP_SERVER: str = "smtp.gmail.com"
SMTP_PORT: int = 465

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_EMAIL_BODY_SIZE = 10000  # Taille maximale en caractères (ajuste si besoin)

def format_alert_message(result: Dict[str, Any], template: str) -> str:
    """
    Format the alert message for a single result using the provided template.
    
    Args:
        result: The result data containing call information
        template: Message template with placeholder keys
        
    Returns:
        Formatted HTML message with result data
    """
    # Handle title as it might be a list or string
    title = result.get("title", "")
    if isinstance(title, list):
        title = ", ".join(title)
    
    # Create a dictionary of all replacements
    replacements = {
        "{title}": title ,
        "{starting_date}": str(result.get("starting_date", "")),
        "{deadline}": str(result.get("deadline", "")),
        "{type}": str(result.get("type", "")),
        "{status}": str(result.get("status", "")),
        "{url}": str(result.get("url", "")),
        "{identifier}": str(result.get("identifier", "")),
        "{reference}": str(result.get("reference", "")),
        "{summary}": str(result.get("summary", "")),
        "{frameworkProgramme}": str(result.get("frameworkProgramme", "")),
    }
    
    # Apply all replacements to the template
    message = template
    for key, value in replacements.items():
        message = message.replace(key, value)
    
    # Format for HTML email
    message = message.replace("\n", "<br>")
    
    # Wrap in a styled div
    return (
        f"<div style='border-top: 1px solid #ccc; margin: 20px 0; padding-top: 10px;'>"
        f"{message}"
        f"</div>"
    )

def build_limited_email_body(results: List[Dict[str, Any]], alert_template: str) -> str:
    """
    Construit le corps de l'email en limitant la taille maximale.
    Si la taille est dépassée, ajoute un message d'avertissement.
    """
    body = ""
    for idx, result in enumerate(results):
        msg = format_alert_message(result, alert_template)
        if len(body) + len(msg) > MAX_EMAIL_BODY_SIZE:
            body += (
                "<div style='color:red; font-weight:bold; margin-top:20px;'>"
                "Trop d'alertes à afficher dans cet email.<br>"
                "Merci de consulter le site pour voir la suite."
                "</div>"
            )
            break
        body += msg
    return body


def send_email_alert(
    results: List[Dict[str, Any]], 
    alert_template: str, 
    receivers: List[str],
    subject: str = SUBJECT
) -> bool:
    """
    Send an email alert with the given results to the specified receivers.
    
    Args:
        results: List of result data to include in the email
        alert_template: Template for formatting each result
        receivers: List of email addresses to send to
        subject: Email subject line, can include total results information
        
    Returns:
        True if email sent successfully, False otherwise
    """
    # Validate inputs
    if not results:
        logger.info("No results to send.")
        return False
    
    if not receivers:
        logger.info("No recipients specified.")
        return False
    
    if not SENDER or not PASSWORD:
        logger.error("Sender credentials are missing.")
        return False
    
    try:
        # Create message container
        msg = MIMEMultipart()
        msg["From"] = SENDER
        msg["To"] = ", ".join(receivers)
        msg["Subject"] = f"{subject} ({len(results)})"
        
        # Call build_limited_email_body once with the entire results list
        body = build_limited_email_body(results, alert_template)
        
        # Add HTML body to email
        msg.attach(MIMEText(body, 'html'))
        
        # Send the email
        return _send_email(msg, receivers)
    
    except Exception as e:
        logger.error(f"Unexpected error preparing email: {e}", exc_info=True)
        return False


def _send_email(msg: MIMEMultipart, receivers: List[str]) -> bool:
    """
    Send the prepared email message.
    
    Args:
        msg: Prepared MIME message
        receivers: List of recipient addresses
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER, PASSWORD)
            server.sendmail(SENDER, receivers, msg.as_string())
            
        logger.info(f"Email sent successfully to {', '.join(receivers)}.")
        return True
        
    except smtplib.SMTPException as smtp_err:
        logger.error(f"SMTP error sending email: {smtp_err}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}", exc_info=True)
        return False
