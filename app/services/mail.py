import os
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
# On n'importe plus "settings", mais on peut importer SECRET_KEY si besoin
from app.config import SECRET_KEY 

# On récupère les variables directement via os.getenv car load_dotenv 
# a déjà été exécuté dans app/config.py
conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD"),
    MAIL_FROM = os.getenv("MAIL_FROM", "noreply@avicenne-pay.fr"),
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER = os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True
)

async def send_reset_password_email(email_to: str, reset_link: str):
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
        recipients=[email_to],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)