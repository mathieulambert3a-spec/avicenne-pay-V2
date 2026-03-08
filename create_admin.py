import asyncio
import sys
import os
from passlib.context import CryptContext
from sqlalchemy import select

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
sys.path.append(os.getcwd())

from app.database import AsyncSessionLocal
from app.models.user import User

async def create_user():
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "superadmin@avicenne.fr")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD manquant")

    # limite bcrypt
    if len(password.encode("utf-8")) > 72:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD > 72 bytes (limite bcrypt)")

    async with AsyncSessionLocal() as session:
        # évite les doublons
        res = await session.execute(select(User).where(User.email == email))
        if res.scalar_one_or_none():
            print(f"ℹ️ Utilisateur déjà existant: {email}")
            return

        new_user = User(
            email=email,
            hashed_password=pwd_context.hash(password),
            role="admin",  # si ton modèle est Enum, on adaptera avec Role.admin
            nom=os.getenv("BOOTSTRAP_ADMIN_NOM", "ADMIN"),
            prenom=os.getenv("BOOTSTRAP_ADMIN_PRENOM", "Principal"),
            profil_complete=True
        )
        session.add(new_user)
        await session.commit()
        print("✅ SUPER ADMIN créé avec succès !")
        print(f"📧 Email : {email}")

if __name__ == "__main__":
    asyncio.run(create_user())