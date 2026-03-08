import asyncio
import random
from datetime import datetime
from sqlalchemy import select
from app.database import SessionLocal
from app.models.user import User, Role, Site, Programme, MATIERES, Filiere, Annee
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
from app.models.mission import Mission
from app.models.sub_mission import SousMission

async def seed_data_pro():
    async with SessionLocal() as db:
        print("🚀 Démarrage du peuplement de la base Neon...")

        # 1. RÉCUPÉRATION DES SOUS-MISSIONS (pour créer des lignes valides)
        result = await db.execute(select(SousMission))
        all_subs = result.scalars().all()
        if not all_subs:
            print("❌ Erreur : Aucune sous-mission en base. Lance d'abord l'initialisation des missions.")
            return

        # 2. CONFIGURATION DES UTILISATEURS
        PASSWORD = "hashed_password_ici" # À remplacer par un vrai hash si besoin
        sites = [Site.lyon_est, Site.lyon_sud]
        programmes = [Programme.pass_, Programme.las1, Programme.las2]
        
        all_new_users = []

        print("👥 Création des 30 utilisateurs...")
        for site in sites:
            suffix = "sud" if site == Site.lyon_sud else "est"
            
            # --- COORDINATEUR (1 par site) ---
            coord = User(
                email=f"coord.{suffix}@avicenne.fr", nom=f"COORDO", prenom=f"{suffix.upper()}",
                role=Role.coordo, site=site, hashed_password=PASSWORD, is_active=True, profil_complete=True
            )
            # --- RESPONSABLES (2 par site) ---
            resps = [
                User(email=f"resp{i}.{suffix}@avicenne.fr", nom=f"RESP{i}", prenom=f"{suffix.upper()}",
                     role=Role.resp, site=site, hashed_password=PASSWORD, is_active=True, profil_complete=True)
                for i in range(1, 3)
            ]
            # --- TCP (12 par site) ---
            tcps = [
                User(email=f"tcp{i}.{suffix}@avicenne.fr", nom=f"DURAND-{suffix.upper()}{i}", prenom="Jean",
                     role=Role.tcp, site=site, hashed_password=PASSWORD, is_active=True, profil_complete=True,
                     programme=random.choice(programmes), filiere=Filiere.medecine, annee=Annee.p2)
                for i in range(1, 13)
            ]
            
            users_site = [coord] + resps + tcps
            db.add_all(users_site)
            all_new_users.extend(users_site)

        await db.flush() # Pour obtenir les IDs

        # 3. GÉNÉRATION DES DÉCLARATIONS (150+)
        print("📊 Génération des déclarations et des lignes...")
        
        # On cible Février (2) et Mars (3) 2026
        for user in all_new_users:
            # --- MARS 2026 (Au moins une par personne) ---
            # On choisit le programme de l'user ou PASS par défaut
            prog = user.programme or Programme.pass_
            
            decl_mars = Declaration(
                user_id=user.id,
                site=user.site,
                programme=prog,
                mois=3,
                annee=2026,
                statut=random.choice([StatutDeclaration.brouillon, StatutDeclaration.soumise, StatutDeclaration.validee]),
                soumise_le=datetime.now() if random.random() > 0.5 else None
            )
            db.add(decl_mars)
            await db.flush()

            # Ajouter 2 à 4 lignes d'activités par déclaration
            for _ in range(random.randint(2, 4)):
                sub = random.choice(all_subs)
                db.add(LigneDeclaration(
                    declaration_id=decl_mars.id,
                    sous_mission_id=sub.id,
                    quantite=random.choice([1.0, 2.0, 5.0, 10.0]) # ex: 2h ou 10 QCM
                ))

            # --- FÉVRIER 2026 (Validée pour 80% des gens) ---
            if random.random() > 0.2:
                decl_feb = Declaration(
                    user_id=user.id, site=user.site, programme=prog,
                    mois=2, annee=2026, statut=StatutDeclaration.validee,
                    soumise_le=datetime(2026, 2, 28)
                )
                db.add(decl_feb)
                await db.flush()
                
                # Activités de février
                for _ in range(3):
                    sub = random.choice(all_subs)
                    db.add(LigneDeclaration(
                        declaration_id=decl_feb.id,
                        sous_mission_id=sub.id,
                        quantite=random.uniform(1.0, 5.0)
                    ))

        # 4. CAS PARTICULIERS : AJOUT DE REJETS
        print("⚠️ Ajout de quelques rejets pour test...")
        for _ in range(15):
            target_user = random.choice(all_new_users)
            decl_rejet = Declaration(
                user_id=target_user.id, site=target_user.site, programme=target_user.programme or Programme.pass_,
                mois=3, annee=2026, statut=StatutDeclaration.brouillon, # Un rejet redevient brouillon
                commentaire_admin="Motif : Justificatif de séance non joint ou heures incohérentes."
            )
            db.add(decl_rejet)

        await db.commit()
        print(f"✅ Terminé ! 30 utilisateurs et environ {150} déclarations injectés sur Neon.")

if __name__ == "__main__":
    asyncio.run(seed_data_pro())