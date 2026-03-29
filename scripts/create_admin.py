# scripts/create_admin.py
import asyncio
import os
import ssl
import sys
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

sys.path.insert(0, ".")

# ── Chargement .env ───────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── Hash IMMÉDIAT — avant tout le reste ───────────────────────────────────
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD  = "ChangeMe123" + chr(33)   # chr(33) = !
HASHED    = pwd_context.hash(PASSWORD)

# Validation immédiate — on plante tôt si ça ne marche pas
assert isinstance(HASHED, str),        f"Hash non-string : {type(HASHED)}"
assert HASHED.startswith("$2b$"),      f"Hash invalide   : {HASHED!r}"
assert len(HASHED) > 50,              f"Hash trop court  : {len(HASHED)}"
assert pwd_context.verify(PASSWORD, HASHED), "Vérification bcrypt échouée !"

print(f"✅ Hash OK : {HASHED[:40]}…  (longueur={len(HASHED)})")

# ── SQLAlchemy SQL pur (sans ORM) ─────────────────────────────────────────
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

EMAIL = "admin@avicenne.fr"


def build_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        sys.exit("❌ DATABASE_URL non définie dans .env")

    url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("postgres://",   "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    qs    = [(k, v) for k, v in parse_qsl(parts.query)
             if k.lower() not in {"sslmode", "channel_binding"}]
    return urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        urlencode(qs), parts.fragment
    ))


async def main() -> None:
    url = build_url()
    host = urlsplit(url).netloc.split("@")[-1]
    print(f"🔗 Connexion : {host}")

    ssl_ctx = ssl.create_default_context()
    engine  = create_async_engine(url, connect_args={"ssl": ssl_ctx}, echo=False)

    try:
        async with engine.begin() as conn:   # begin() = auto-commit ou rollback

            # ── Existe déjà ? ─────────────────────────────────────────────
            row = (await conn.execute(
                text("SELECT id FROM users WHERE email = :e"),
                {"e": EMAIL}
            )).fetchone()

            if row:
                print(f"ℹ️  Admin existant (id={row[0]}) — mise à jour du mot de passe")
                await conn.execute(
                    text("""
                        UPDATE users
                           SET hashed_password = :hp,
                               is_active        = TRUE,
                               updated_at       = NOW()
                         WHERE email = :e
                    """),
                    {"hp": HASHED, "e": EMAIL},
                )
            else:
                print("➕ Création de l'admin")
                await conn.execute(
                    text("""
                        INSERT INTO users 
                            (is_active, email, hashed_password, 
                             role, nom, prenom, site,
                             created_at, updated_at)
                        VALUES 
                            (TRUE, :email, :hp, 
                             'admin', 'Admin', 'Avicenne', NULL,
                             NOW(), NOW())
                    """),
                    {"email": EMAIL, "hp": HASHED},
                )

            # ── Vérification dans la même transaction ──────────────────────
            check = (await conn.execute(
                text("""
                    SELECT id, email, role, is_active,
                           hashed_password
                      FROM users
                     WHERE email = :e
                """),
                {"e": EMAIL},
            )).fetchone()

        # Hors du `async with` → transaction commitée
        if check is None:
            sys.exit("❌ Ligne introuvable après commit")

        hp_db = check[4]
        print(f"\n--- Vérification post-commit ---")
        print(f"  id       = {check[0]}")
        print(f"  email    = {check[1]}")
        print(f"  role     = {check[2]}")
        print(f"  actif    = {check[3]}")
        print(f"  hash_db  = {hp_db[:40] if hp_db else 'NULL'}…")

        if not hp_db:
            sys.exit("❌ hashed_password est NULL en base après commit !")

        if not pwd_context.verify(PASSWORD, hp_db):
            sys.exit("❌ Le hash en base ne correspond pas au mot de passe !")

        print(f"\n✅ SUCCÈS")
        print(f"   Email    : {EMAIL}")
        print(f"   Password : {PASSWORD}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
