import os
import sys
import asyncio
import getpass

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from passlib.context import CryptContext
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    email = os.getenv("EMAIL") or input("Email: ").strip()
    password = os.getenv("NEW_PASSWORD") or getpass.getpass("New password: ")

    if len(password.encode("utf-8")) > 72:
        raise SystemExit("❌ Mot de passe > 72 bytes (limite bcrypt). Choisis plus court.")

    async with AsyncSessionLocal() as s:
        r = await s.execute(select(User).where(User.email == email))
        u = r.scalar_one_or_none()
        if not u:
            raise SystemExit(f"❌ User introuvable: {email}")

        u.hashed_password = pwd_context.hash(password)
        await s.commit()

    print(f"✅ Mot de passe mis à jour pour {email}")


if __name__ == "__main__":
    asyncio.run(main())