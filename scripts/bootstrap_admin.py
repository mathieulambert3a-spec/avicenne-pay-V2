import asyncio
import os

from passlib.context import CryptContext
from sqlalchemy import select

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from app.database import AsyncSessionLocal
from app.models.user import User, Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "superadmin@avicenne.fr")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD manquant")

    if len(password.encode("utf-8")) > 72:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD > 72 bytes (limite bcrypt)")

    async with AsyncSessionLocal() as s:
        r = await s.execute(select(User).where(User.email == email))
        u = r.scalar_one_or_none()

        if u:
            u.hashed_password = pwd_context.hash(password)
            u.role = Role.admin
            print("✅ Admin existant: mot de passe mis à jour")
        else:
            u = User(
                email=email,
                hashed_password=pwd_context.hash(password),
                role=Role.admin,
                nom=os.getenv("BOOTSTRAP_ADMIN_NOM", "ADMIN"),
                prenom=os.getenv("BOOTSTRAP_ADMIN_PRENOM", "Principal"),
                profil_complete=True,
            )
            s.add(u)
            print("✅ Admin créé")

        await s.commit()
        print("📧", email)


if __name__ == "__main__":
    asyncio.run(main())