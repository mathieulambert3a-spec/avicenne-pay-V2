import asyncio
import random
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from cryptography.fernet import Fernet

from app.routers.auth import pwd_context 
from app.database import AsyncSessionLocal
from app.config import FERNET_KEY
from app.models.user import User, Role, Site, Programme
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
from app.schemas.constants import MISSIONS_INITIALES

# --- CONFIGURATION CHIFFREMENT ---
def encrypt_seed(value: str) -> str:
    if not FERNET_KEY or not value:
        return value
    f = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return f.encrypt(value.encode()).decode()

# Matières cibles pour le PASS
MATIERES_PASS = ["UE_1", "UE_2", "UE_3", "UE_4", "UE_5"]

async def reset_and_seed():
    async with AsyncSessionLocal() as db:
        print("🧹 1. Nettoyage de la base (Déclarations et utilisateurs @avicenne.fr)...")
        # Nettoyage global pour éviter les conflits d'index ou de FK
        await db.execute(delete(LigneDeclaration))
        await db.execute(delete(Declaration))
        await db.execute(delete(User).where(User.email.like('%@avicenne.fr')))
        await db.execute(delete(SousMission))
        await db.execute(delete(Mission))
        await db.commit()

        # --- ÉTAPE 2 : RECONSTRUCTION DU CATALOGUE ---
        print("♻️ 2. Reconstruction du catalogue...")
        for index, (mission_nom, subs) in enumerate(MISSIONS_INITIALES.items()):
            is_resp_parent = any(s.get("is_resp", False) for s in subs)
            new_m = Mission(titre=mission_nom, resp_only=is_resp_parent, ordre=index, is_active=True)
            db.add(new_m)
            await db.flush() 

            for sub_index, sub_data in enumerate(subs):
                new_sm = SousMission(
                    mission_id=new_m.id, titre=sub_data["titre"], tarif=sub_data["tarif"],
                    unite=sub_data.get("unite", "heure"), ordre=sub_index, is_active=True
                )
                db.add(new_sm)
        await db.commit()

        print("⚙️ 3. Chargement du pool de missions...")
        result = await db.execute(select(SousMission).options(selectinload(SousMission.mission)))
        all_subs = result.scalars().all()
        subs_classiques = [s for s in all_subs if not s.mission.resp_only]
        subs_resp_only = [s for s in all_subs if s.mission.resp_only]

        print("👥 4. Création des utilisateurs (Lyon Est / PASS uniquement)...")
        PASSWORD_RAW = "Avicenne_Pay_2026!"
        PASSWORD_HASH = pwd_context.hash(PASSWORD_RAW)
        all_new_users = []

        # --- A. L'ADMIN principal (Identifiant identique au script d'origine) ---
        admin_user = User(
            email="admin@avicenne.fr", nom="ADMIN", prenom="System",
            role=Role.admin, site=Site.lyon_est, hashed_password=PASSWORD_HASH, 
            is_active=True, profil_complete=True,
            adresse="1 Rue de l'Administration", code_postal="69008", ville="Lyon"
        )
        db.add(admin_user)

        # --- B. Le COORDINATEUR (Lyon Est uniquement) ---
        coordo = User(
            email="coordo.lyon.est@avicenne.fr", nom="COORDO", prenom="Est",
            role=Role.coordo, site=Site.lyon_est, hashed_password=PASSWORD_HASH, 
            is_active=True, profil_complete=True,
            adresse="Bureau des Coordinateurs Lyon Est", code_postal="69000", ville="Lyon",
            nss_encrypted=encrypt_seed("1000000000"),
            iban_encrypted=encrypt_seed("FR760000000001")
        )
        db.add(coordo)

        # --- C. Les 5 RESP (Un par UE pour l'index unique) ---
        for i, ue in enumerate(MATIERES_PASS, 1):
            u = User(
                email=f"resp{i}@avicenne.fr", nom=f"RESP{i}", prenom="Test",
                role=Role.resp, site=Site.lyon_est, programme=Programme.pass_,
                matiere=ue, hashed_password=PASSWORD_HASH, is_active=True, profil_complete=True,
                adresse=f"{i} Rue du Resp", code_postal="69000", ville="Lyon",
                nss_encrypted=encrypt_seed("2000000000"), iban_encrypted=encrypt_seed(f"FR76RESP000{i}")
            )
            db.add(u)
            all_new_users.append(u)

        # --- D. Les 9 TCP ---
        for i in range(1, 10):
            u = User(
                email=f"tcp{i}@avicenne.fr", nom=f"TCP{i}", prenom="Test",
                role=Role.tcp, site=Site.lyon_est, programme=Programme.pass_,
                matiere=random.choice(MATIERES_PASS), 
                hashed_password=PASSWORD_HASH, is_active=True, profil_complete=True,
                adresse=f"{i} Rue du TCP", code_postal="69000", ville="Lyon",
                nss_encrypted=encrypt_seed("3000000000"), iban_encrypted=encrypt_seed(f"FR76TCP000{i}")
            )
            db.add(u)
            all_new_users.append(u)

        await db.flush()

        print("📊 5. Génération de 14 déclarations pour Mars...")
        # Mélange des 14 utilisateurs (5 RESP + 9 TCP) pour distribuer les statuts
        random.shuffle(all_new_users)
        
        for idx, user in enumerate(all_new_users):
            # 4 validées, les 10 autres en brouillon
            statut = StatutDeclaration.validee if idx < 4 else StatutDeclaration.brouillon
            
            decl = Declaration(
                user_id=user.id, site=user.site, programme=user.programme,
                mois=3, annee=2026, statut=statut,
                soumise_le=datetime.now() if statut == StatutDeclaration.validee else None
            )
            db.add(decl)
            await db.flush()

            # Lignes de déclaration (Missions)
            pool = subs_resp_only if user.role == Role.resp else subs_classiques
            chosen_subs = random.sample(pool, k=min(len(pool), 3))
            
            for sub in chosen_subs:
                db.add(LigneDeclaration(
                    declaration_id=decl.id, sous_mission_id=sub.id,
                    quantite=float(random.randint(2, 10))
                ))

        await db.commit()
        print(f"✅ Succès ! {len(all_new_users) + 2} utilisateurs créés au total.")
        print(f"🔑 Login Admin : admin@avicenne.fr / {PASSWORD_RAW}")
        print(f"🚀 14 déclarations injectées pour Mars (4 validées).")

if __name__ == "__main__":
    asyncio.run(reset_and_seed())