import os
import logging
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from app.config import SECRET_KEY 

# Configuration des logs pour voir ce qui se passe
logger = logging.getLogger("uvicorn")

conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD"),
    MAIL_FROM = os.getenv("MAIL_FROM", "admin@avicenne.fr"),
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER = os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

async def send_reset_password_email(email: str, reset_link: str):
    """
    Envoie un email de réinitialisation de mot de passe.
    """
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px;">
        <h2 style="color: #0d6efd;">Avicenne Pay</h2>
        <p>Bonjour,</p>
        <p>Vous avez demandé la réinitialisation de votre mot de passe. Cliquez sur le bouton ci-dessous pour procéder :</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background-color: #0d6efd; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Réinitialiser mon mot de passe</a>
        </div>
        <p style="color: #666; font-size: 0.9em;">Ce lien expirera dans 30 minutes. Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 20px;">
        <p style="font-size: 0.8em; color: #999;">Ceci est un message automatique, merci de ne pas y répondre.</p>
    </div>
    """
    
    message = MessageSchema(
        subject="Réinitialisation de votre mot de passe - Avicenne Pay",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    try:
        # --- MODE SIMULATION (Quota/Pare-feu) ---
        # fm = FastMail(conf)
        # await fm.send_message(message)
        logger.warning(f"📩 SIMULATION : Reset mot de passe envoyé à {email}")
        return True
    except Exception as e:
        logger.error(f"❌ ÉCHEC ENVOI RESET ({email}) : {str(e)}")
        return False

async def send_welcome_email(email: str, setup_link: str):
    """
    Envoie un email de bienvenue lors de la création d'un compte.
    """
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 10px;">
        <h2 style="color: #0d6efd;">Bienvenue sur Avicenne Pay</h2>
        <p>Bonjour,</p>
        <p>Votre compte a été créé par l'administration. Pour finaliser votre inscription et choisir votre mot de passe, cliquez sur le bouton ci-dessous :</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{setup_link}" style="background-color: #198754; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                Activer mon compte
            </a>
        </div>
        <p style="color: #666; font-size: 0.9em;">Ce lien de sécurité est valable pour votre première connexion. Si vous rencontrez des difficultés, contactez votre administrateur.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 20px;">
        <p style="font-size: 0.8em; color: #999;">Ceci est un message automatique de la plateforme Avicenne.</p>
    </div>
    """
    
    message = MessageSchema(
        subject="Création de votre compte - Avicenne Pay",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    try:
        # --- MODE SIMULATION (Quota/Pare-feu) ---
        # fm = FastMail(conf)
        # await fm.send_message(message)
        logger.warning(f"📩 SIMULATION : Bienvenue envoyé à {email}")
        return True
    except Exception as e:
        logger.error(f"❌ ÉCHEC ENVOI BIENVENUE ({email}) : {str(e)}")
        return False
    
async def send_reminder_email(email: str, link: str, month_fr: str = "Mars"):
    """
    Envoie un email de relance stylisé pour les retardataires (Simulation active).
    """
    html_content = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 10px; overflow: hidden;">
        <div style="background-color: #0d6efd; padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">Avicenne Pay</h1>
        </div>
        
        <div style="padding: 30px; color: #444; line-height: 1.6;">
            <p style="font-size: 16px;">Bonjour,</p>
            <p>Sauf erreur de notre part, vous n'avez pas encore finalisé votre déclaration d'activité pour le mois de <strong>{month_fr} 2026</strong>.</p>
            <p>Pour rappel, la saisie de vos activités est nécessaire pour le traitement de votre dossier.</p>
            
            <div style="text-align: center; margin: 40px 0;">
                <a href="{link}" style="background-color: #ffca2c; color: #000; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: inline-block;">
                    Compléter ma déclaration
                </a>
            </div>
            
            <p style="font-size: 13px; color: #888;">Si vous avez soumis votre déclaration récemment, vous pouvez ignorer cet email.</p>
        </div>
        
        <div style="background-color: #f8f9fa; padding: 15px; text-align: center; border-top: 1px solid #eee;">
            <p style="font-size: 12px; color: #aaa; margin: 0;">&copy; 2026 Avicenne Pay - Système de relance automatique</p>
        </div>
    </div>
    """

    message = MessageSchema(
        subject=f"Rappel : Votre déclaration de {month_fr} est attendue",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )

    try:
        # --- MODE SIMULATION (Quota Mailtrap / Pare-feu entreprise) ---
        # fm = FastMail(conf)
        # await fm.send_message(message)
        
        logger.warning(f"📩 SIMULATION : Relance envoyée à {email} pour {month_fr}")
        return True
    except Exception as e:
        logger.error(f"❌ ÉCHEC ENVOI RELANCE ({email}) : {str(e)}")
        return False