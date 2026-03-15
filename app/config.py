import os
from dotenv import load_dotenv
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer
from passlib.context import CryptContext

# dossier racine du projet
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
FERNET_KEY = os.getenv("FERNET_KEY")
        
# DÉFINITIONS
serializer = URLSafeTimedSerializer(SECRET_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")