# app/services.py
from itsdangerous import URLSafeTimedSerializer
from app.config import settings # Assure-toi d'avoir une SECRET_KEY dans ton config.py

def get_password_reset_serializer():
    # On utilise la SECRET_KEY de ton appli pour signer le token
    return URLSafeTimedSerializer(settings.SECRET_KEY)

def generate_password_reset_token(email: str):
    serializer = get_password_reset_serializer()
    # Le token contient l'email de l'utilisateur
    return serializer.dumps(email, salt="password-reset-salt")

def verify_password_reset_token(token: str, expiration=1800):
    """
    Vérifie le token et retourne l'email si valide.
    expiration: 1800 secondes (30 minutes)
    """
    serializer = get_password_reset_serializer()
    try:
        email = serializer.loads(
            token,
            salt="password-reset-salt",
            max_age=expiration
        )
        return email
    except Exception:
        return None