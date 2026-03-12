import os
import sys
import asyncio
import random
from datetime import datetime
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload
from cryptography.fernet import Fernet

# On importe le pwd_context directement depuis ton routeur auth pour la cohérence du hash
from app.routers.auth import pwd_context 
from app.database import AsyncSessionLocal
from app.config import FERNET_KEY
from app.models.user import User, Role, Site, Programme
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
import asyncio
from app.schemas.constants import MISSIONS_INITIALES

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

async def reset_and_seed():
    async with AsyncSessionLocal() as db:
        print("🧹 1. Nettoyage de la base (Déclarations et utilisateurs @avicenne.fr)...")
        
        # On récupère les IDs des users test pour supprimer leurs déclarations
        user_ids_query = await db.execute(select(User.id).where(User.email.like('%@avicenne.fr')))
        test_user_ids = user_ids_query.scalars().all()
        
        if test_user_ids:
            decl_ids_query = await db.execute(select(Declaration.id).where(Declaration.user_id.in_(test_user_ids)))
            test_decl_ids = decl_ids_query.scalars().all()
            if test_decl_ids:
                await db.execute(delete(LigneDeclaration).where(LigneDeclaration.declaration_id.in_(test_decl_ids)))
                await db.execute(delete(Declaration).where(Declaration.id.in_(test_decl_ids)))
            await db.execute(delete(User).where(User.id.in_(test_user_ids)))

        # --- ÉTAPE 2 : RECONSTRUCTION DU CATALOGUE ---
        print("♻️ 2. Reconstruction du catalogue des missions et sous-missions...")
        await db.execute(delete(SousMission))
        await db.execute(delete(Mission))
        await db.commit() 

        for index, (mission_nom, subs) in enumerate(MISSIONS_INITIALES.items()):
            # Vérification si c'est une mission réservée aux responsables
            is_resp_parent = any(s.get("is_resp", False) for s in subs)
            
            new_m = Mission(
                titre=mission_nom, 
                resp_only=is_resp_parent,
                ordre=index,
                is_active=True # <-- Assure la visibilité immédiate
            )
            db.add(new_m)
            await db.flush() 

            for sub_index, sub_data in enumerate(subs):
                new_sm = SousMission(
                    mission_id=new_m.id,
                    titre=sub_data["titre"],
                    tarif=sub_data["tarif"],
                    unite=sub_data.get("unite", "heure"),
                    ordre=sub_index,
                    is_active=True
                )
                db.add(new_sm)
        
        await db.commit()
        # -------------------------------------------------------------

        print("⚙️ 3. Chargement du nouveau pool de missions...")
        # On recharge les sous-missions avec leurs missions parentes pour le filtrage du seed
        result = await db.execute(select(SousMission).options(selectinload(SousMission.mission)))
        all_subs = result.scalars().all()
        
        subs_classiques = [s for s in all_subs if not s.mission.resp_only]
        subs_resp_only = [s for s in all_subs if s.mission.resp_only]
        
        # On identifie la sous-mission spécifique pour la règle des Responsables
        sub_gestion_equipe = next((s for s in all_subs if "gestion d'équipe" in s.mission.titre.lower()), None)

        print("👥 4. Création des 35 utilisateurs...")
        PASSWORD_RAW = "Avicenne_Pay_2026!"
        PASSWORD_HASH = pwd_context.hash(PASSWORD_RAW)
        
        all_new_users = []
        resp_registry = set()

        # --- A. L'ADMIN principal ---
        admin_user = User(
            email="admin@avicenne.fr", nom="ADMIN", prenom="System",
            role=Role.admin, site=None, hashed_password=PASSWORD_HASH, 
            is_active=True, profil_complete=True,
            adresse="1 Rue de l'Administration", code_postal="69008", ville="Lyon"
        )
        db.add(admin_user)
        all_new_users.append(admin_user)

        # --- B. Les 2 COORDINATEURS ---
        for site_coordo in [Site.lyon_est, Site.lyon_sud]:
            email_clean = f"coordo.{site_coordo.value.lower().replace(' ', '.')}@avicenne.fr"
            coordo = User(
                email=email_clean,
                nom="COORDO", prenom=site_coordo.value.capitalize(),
                role=Role.coordo, site=site_coordo,
                hashed_password=PASSWORD_HASH, 
                is_active=True, profil_complete=True,
                adresse=f"Bureau des Coordinateurs {site_coordo.value}",
                code_postal="69000", ville="Lyon",
                nss_encrypted=encrypt_seed("1000000000"),
                iban_encrypted=encrypt_seed("FR760000000001")
            )
            db.add(coordo)
            all_new_users.append(coordo)

        # --- C. Les 32 autres utilisateurs (RESP et TCP) ---
        for i in range(1, 33):
            site = random.choice([Site.lyon_est, Site.lyon_sud])
            prog = random.choice(list(Programme))
            mat = random.choice(MATIERES.get(prog.value, ["Général"]))
            
            combo = (site, prog, mat)
            role = Role.tcp
            if combo not in resp_registry and random.random() > 0.6:
                role = Role.resp
                resp_registry.add(combo)

            u = User(
                email=f"user{i}@avicenne.fr", nom=f"USER{i}", prenom="Test",
                role=role, site=site, programme=prog, matiere=mat,
                hashed_password=PASSWORD_HASH, is_active=True, profil_complete=True,
                adresse=f"{i} Rue du Test", code_postal="69000", ville="Lyon",
                nss_encrypted=encrypt_seed("1234567890"),
                iban_encrypted=encrypt_seed("FR760000000000")
            )
            db.add(u)
            all_new_users.append(u)

        await db.flush()

        print(f"📊 5. Génération des déclarations (Janvier -> Mars)...")
        count_decl = 0
        soumises_fevrier_count = 0

        for user in all_new_users:
            if user.role in [Role.admin, Role.coordo]: 
                continue 

            for mois in [1, 2, 3]: # Janvier, Février, Mars
                if mois == 1:
                    statut = StatutDeclaration.validee
                elif mois == 2:
                    if soumises_fevrier_count < 2:
                        statut = StatutDeclaration.soumise
                        soumises_fevrier_count += 1
                    else:
                        statut = StatutDeclaration.validee
                else: # Mars
                    statut = StatutDeclaration.brouillon
                
                decl = Declaration(
                    user_id=user.id, site=user.site, programme=user.programme,
                    mois=mois, annee=2026, statut=statut,
                    soumise_le=datetime.now() if statut in [StatutDeclaration.soumise, StatutDeclaration.validee] else None
                )
                db.add(decl)
                await db.flush()
                count_decl += 1

                # --- GESTION DES LIGNES ---
                used_sub_ids = set()

                if user.role == Role.resp and sub_gestion_equipe:
                    db.add(LigneDeclaration(
                        declaration_id=decl.id, 
                        sous_mission_id=sub_gestion_equipe.id,
                        quantite=1.0
                    ))
                    used_sub_ids.add(sub_gestion_equipe.id)

                target_total = random.randint(2, 5)
                pool = subs_resp_only if user.role == Role.resp else subs_classiques
                
                # Filtrage : On évite de seeder aléatoirement des missions d'été ou de formation
                pool = [
                    s for s in pool 
                    if "mise à jour estivale" not in s.mission.titre.lower() 
                    and "formation" not in s.mission.titre.lower()
                ]
                if user.role == Role.tcp:
                    pool = [s for s in pool if "gestion d'équipe" not in s.mission.titre.lower()]

                random.shuffle(pool)
                for sub in pool:
                    if len(used_sub_ids) >= target_total:
                        break
                    if sub.id not in used_sub_ids:
                        db.add(LigneDeclaration(
                            declaration_id=decl.id, 
                            sous_mission_id=sub.id,
                            quantite=float(random.randint(2, 12))
                        ))
                        used_sub_ids.add(sub.id)

        await db.commit()
        print(f"✅ Succès ! Catalogue réordonné et {len(all_new_users)} utilisateurs créés.")
        print(f"🔑 Logins coordos : coordo.lyon.est@avicenne.fr et coordo.lyon.sud@avicenne.fr")
        print(f"🚀 {count_decl} déclarations injectées.")

if __name__ == "__main__":
    asyncio.run(reset_and_seed())