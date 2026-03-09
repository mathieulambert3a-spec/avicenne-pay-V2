import asyncio
import random
from datetime import datetime
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from cryptography.fernet import Fernet

from app.database import AsyncSessionLocal
from app.config import FERNET_KEY
from app.models.user import User, Role, Site, Programme, Filiere, Annee
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration

# --- CONFIGURATION CHIFFREMENT ---
def encrypt_seed(value: str) -> str:
    if not FERNET_KEY or not value:
        return value
    f = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return f.encrypt(value.encode()).decode()

MATIERES = {
    "PASS": ["UE_1", "UE_2", "UE_3", "UE_4", "UE_5", "UE_6", "UE_7", "UE_8", "MMOK", "PHARMA", "ORAUX"],
    "LAS 1": ["Physiologie", "Anatomie", "Biologie Cell", "Biochimie", "Biostats", "SSH"],
    "LAS 2": ["Microbiologie", "Biocell / Immuno", "Biologie Dev", "Génétique", "Physiologie"]
}

async def seed_data_pro():
    async with AsyncSessionLocal() as db:
        print("🚀 Démarrage du peuplement de la base...")

        # 1. NETTOYAGE
        user_ids_query = await db.execute(select(User.id).where(User.email.like('%@avicenne.fr')))
        test_user_ids = user_ids_query.scalars().all()
        if test_user_ids:
            decl_ids_query = await db.execute(select(Declaration.id).where(Declaration.user_id.in_(test_user_ids)))
            test_decl_ids = decl_ids_query.scalars().all()
            if test_decl_ids:
                await db.execute(delete(LigneDeclaration).where(LigneDeclaration.declaration_id.in_(test_decl_ids)))
                await db.execute(delete(Declaration).where(Declaration.id.in_(test_decl_ids)))
            await db.execute(delete(User).where(User.id.in_(test_user_ids)))
        await db.commit()

        # 2. CONFIGURATION DES MISSIONS
        # Marquer les missions de gestion comme réservées aux RESP
        await db.execute(
            update(Mission)
            .where(Mission.titre.ilike("%Gestion%"))
            .values(resp_only=True)
        )
        await db.commit()

        # Chargement Eager (selectinload) pour éviter l'erreur Greenlet
        result = await db.execute(
            select(SousMission).options(selectinload(SousMission.mission))
        )
        all_subs = result.scalars().all()
        
        subs_classiques = [s for s in all_subs if not s.mission.resp_only]
        subs_resp_only = [s for s in all_subs if s.mission.resp_only]

        # 3. CRÉATION DES UTILISATEURS
        PASSWORD = "$2b$12$zQd4INMd4dEgvrJ5D/n01unYIIDK7t3w6IJSe2odXDxOLZOeeeJGe"
        sites = [Site.lyon_est, Site.lyon_sud]
        all_new_users = []

        # --- ADMIN ---
        admin_user = User(
            email="admin@avicenne.fr", nom="ADMIN", prenom="System",
            role=Role.admin, site=None, hashed_password=PASSWORD, 
            is_active=True, profil_complete=True,
            adresse="1 Rue de l'Administration", code_postal="69008", ville="Lyon"
        )
        db.add(admin_user)

        for site in sites:
            suffix = "sud" if site == Site.lyon_sud else "est"
            
            # COORDINATEUR
            coord = User(
                email=f"coord.{suffix}@avicenne.fr", nom="COORDO", prenom=suffix.upper(),
                role=Role.coordo, site=site, hashed_password=PASSWORD, 
                is_active=True, profil_complete=True,
                adresse=f"Site {suffix.upper()}", code_postal="69000", ville="Lyon"
            )
            db.add(coord)

            # RESPONSABLES et TCP
            for role_type, count in [(Role.resp, 2), (Role.tcp, 5)]:
                for i in range(1, count + 1):
                    p = random.choice(list(Programme))
                    m = random.choice(MATIERES.get(p.value, ["Général"]))
                    
                    u = User(
                        email=f"{role_type.value}{i}.{suffix}@avicenne.fr", 
                        nom=f"{role_type.value.upper()}{i}", prenom=suffix.upper(),
                        role=role_type, site=site, hashed_password=PASSWORD, 
                        is_active=True, profil_complete=True, 
                        programme=p, matiere=m,
                        adresse=f"{random.randint(1, 150)} Avenue des Testeurs",
                        code_postal="69008", ville="Lyon",
                        nss_encrypted=encrypt_seed("185016912345678"),
                        iban_encrypted=encrypt_seed("FR7630006000011234567890123")
                    )
                    db.add(u)
                    all_new_users.append(u)

        await db.flush() 

        # 4. GÉNÉRATION DES DÉCLARATIONS (HISTORIQUE 5 MOIS)
        print("📊 Génération de l'historique (Octobre 2025 -> Février 2026)...")
        
        # On définit l'historique par rapport à "aujourd'hui" (Mars 2026 dans ton contexte)
        historique = [
            (10, 2025, StatutDeclaration.validee),
            (11, 2025, StatutDeclaration.validee),
            (12, 2025, StatutDeclaration.validee),
            (1, 2026, StatutDeclaration.soumise),
            (2, 2026, StatutDeclaration.brouillon) # Mois d'Avril ou Février selon tes besoins
        ]

        for user in all_new_users:
            if user.role in [Role.admin, Role.coordo]: continue

            for mois, annee, statut_defaut in historique:
                decl = Declaration(
                    user_id=user.id, site=user.site, programme=user.programme,
                    mois=mois, annee=annee, statut=statut_defaut, 
                    soumise_le=datetime.now() if statut_defaut != StatutDeclaration.brouillon else None
                )
                db.add(decl)
                await db.flush() 

                # A. Forfait RESP uniquement
                if user.role == Role.resp and subs_resp_only:
                    for s_resp in subs_resp_only:
                        db.add(LigneDeclaration(
                            declaration_id=decl.id, 
                            sous_mission_id=s_resp.id,
                            quantite=1.0
                        ))

                # B. Heures classiques
                for _ in range(random.randint(1, 3)):
                    if subs_classiques:
                        db.add(LigneDeclaration(
                            declaration_id=decl.id, 
                            sous_mission_id=random.choice(subs_classiques).id,
                            quantite=float(random.randint(2, 10))
                        ))

        await db.commit()
        print(f"✅ Terminé ! Profils injectés et historique créé.")

if __name__ == "__main__":
    asyncio.run(seed_data_pro())