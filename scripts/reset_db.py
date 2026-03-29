import asyncio
import os
import ssl
import sys
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from passlib.context import CryptContext
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

# Configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ADMIN_EMAIL = "admin@avicenne.fr"
ADMIN_PASS = "ChangeMe123!"
HASHED = pwd_context.hash(ADMIN_PASS)

def clean_database_url(raw_url: str) -> str:
    """Transforme l'URL pour asyncpg et retire sslmode."""
    if not raw_url:
        sys.exit("❌ DATABASE_URL non définie dans .env")
    
    # Remplacement du driver
    url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Nettoyage des query params (suppression de sslmode)
    parts = urlsplit(url)
    qs = [(k, v) for k, v in parse_qsl(parts.query) 
          if k.lower() not in {"sslmode", "channel_binding"}]
    
    return urlunsplit((
        parts.scheme, parts.netloc, parts.path, 
        urlencode(qs), parts.fragment
    ))

async def reset_database():
    raw_url = os.environ.get("DATABASE_URL")
    url = clean_database_url(raw_url)
    
    # Configuration SSL pour les bases distantes (Heroku/Neon/etc.)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    engine = create_async_engine(url, connect_args={"ssl": ssl_ctx})

    print(f"⚠️  CONNEXION : {urlsplit(url).netloc.split('@')[-1]}")
    print("⚠️  NETTOYAGE COMPLET...")

    try:
        async with engine.begin() as conn:
            # Ordre des tables : adapte selon tes noms exacts
            await conn.execute(text("""
                TRUNCATE TABLE users, declarations 
                RESTART IDENTITY CASCADE;
            """))
            print("✅ Tables vidées.")

            print(f"➕ Création de l'admin : {ADMIN_EMAIL}")
            await conn.execute(
                text("""
                    INSERT INTO users 
                        (is_active, email, hashed_password, role, nom, prenom, created_at, updated_at)
                    VALUES 
                        (TRUE, :email, :hp, 'admin'::role_enum, 'Admin', 'Avicenne', NOW(), NOW())
                """),
                {"email": ADMIN_EMAIL, "hp": HASHED},
            )

        print("\n✨ BASE DE DONNÉES RESET AVEC SUCCÈS.")
    except Exception as e:
        print(f"❌ Erreur lors du reset : {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    confirm = input("❗ VOULEZ-VOUS VRAIMENT TOUT SUPPRIMER ? (oui/non) : ")
    if confirm.lower() == 'oui':
        asyncio.run(reset_database())
    else:
        print("Annulé.")