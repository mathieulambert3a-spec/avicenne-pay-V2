import asyncio
from sqlalchemy import select, delete
from cryptography.fernet import Fernet

# Imports de ton projet
from app.routers.auth import pwd_context 
from app.database import AsyncSessionLocal
from app.config import FERNET_KEY
from app.models.user import User, Role
from app.models.declaration import Declaration, LigneDeclaration
from app.models.mission import Mission
from app.models.sub_mission import SousMission  # Vérifie bien le nom du fichier/modèle

# --- CONFIGURATION CHIFFREMENT ---
def encrypt_seed(value: str) -> str:
    if not FERNET_KEY or not value:
        return value
    f = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return f.encrypt(value.encode()).decode()

async def reset_to_admin_only():
    async with AsyncSessionLocal() as db:
        print("🧹 1. Nettoyage intégral des données exceptées les missions")
        
        # 1. Supprimer les données liées aux déclarations
        print("   - Suppression des lignes de déclaration...")
        await db.execute(delete(LigneDeclaration))
        print("   - Suppression des déclarations...")
        await db.execute(delete(Declaration))
        
        # 2. Supprimer tous les utilisateurs
        print("   - Suppression des utilisateurs...")
        await db.execute(delete(User))
        
        await db.commit()
        print("🗑️  Base vidée sauf les missions (sauf logs éventuels).")

        print("👥 2. Création du compte ADMIN unique...")
        PASSWORD_RAW = "Avicenne_Pay_2026!"
        PASSWORD_HASH = pwd_context.hash(PASSWORD_RAW)
        
        admin_user = User(
            email="admin@avicenne.fr", 
            nom="ADMIN", 
            prenom="System",
            role=Role.admin, 
            site=None, 
            hashed_password=PASSWORD_HASH, 
            is_active=True, 
            profil_complete=True,
            adresse="1 Rue de l'Administration", 
            code_postal="69008", 
            ville="Lyon"
        )
        
        db.add(admin_user)
        await db.commit()
        
        print(f"✅ Succès ! Base vierge et ADMIN créé.")
        print(f"🔑 Mot de passe : {PASSWORD_RAW}")

if __name__ == "__main__":
    asyncio.run(reset_to_admin_only())