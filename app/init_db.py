import asyncio
import sys
from sqlalchemy import select, text
from app.database import engine, Base, AsyncSessionLocal

# IMPORT DES MODÈLES (Crucial pour que SQLAlchemy crée les tables et les INDEX)
from app.models.user import User, Role
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration

# Tentative d'import des constantes
try:
    from app.schemas.constants import MISSIONS_INITIALES
except ImportError as e:
    print(f"❌ Erreur d'import des constantes : {e}")
    sys.exit(1)

async def init_db():
    print("🚀 Démarrage de l'initialisation de la base de données...")
    
    # 1. RÉINITIALISATION DES TABLES
    async with engine.begin() as conn:
        print("🧹 Suppression des anciennes tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("🏗️ Création des nouvelles tables et des index...")
        await conn.run_sync(Base.metadata.create_all)
        
        # Vérification optionnelle de l'index sur Neon
        print("📌 Index 'uq_resp_site_programme_matiere' activé via le modèle User.")

    async with AsyncSessionLocal() as session:
        # 2. INSERTION DES MISSIONS ET SOUS-MISSIONS
        if not MISSIONS_INITIALES:
            print("⚠️ MISSIONS_INITIALES est vide, aucune mission insérée.")
        else:
            print("🌱 Insertion des missions...")
            for m_idx, (m_titre, subs) in enumerate(MISSIONS_INITIALES.items()):
                # On détermine si c'est une mission de gestion (pour le flag resp_only)
                is_gestion = "Gestion" in m_titre
                mission = Mission(titre=m_titre, ordre=m_idx, is_active=True, resp_only=is_gestion)
                session.add(mission)
                await session.flush()
                
                for s_idx, s in enumerate(subs):
                    sm = SousMission(
                        mission_id=mission.id,
                        titre=s["titre"],
                        unite=s["unite"],
                        tarif=s["tarif"],
                        ordre=s_idx,
                        is_active=True
                    )
                    session.add(sm)
            print(f"✅ {len(MISSIONS_INITIALES)} missions insérées.")

        # 3. CRÉATION DE L'ADMINISTRATEUR PAR DÉFAUT
        print("👤 Création de l'administrateur système...")
        # Hash correspondant à 'admin123'
        PASSWORD_HASH = "$2b$12$zQd4INMd4dEgvrJ5D/n01unYIIDK7t3w6IJSe2odXDxOLZOeeeJGe"
        
        admin = User(
            email="admin@avicenne.fr",
            nom="ADMIN",
            prenom="System",
            role=Role.admin,
            hashed_password=PASSWORD_HASH,
            is_active=True,
            profil_complete=True,
            adresse="1 Rue de l'Administration",
            code_postal="69008",
            ville="Lyon"
        )
        session.add(admin)
        
        try:
            await session.commit()
            print("✨ Base de données prête et Admin créé !")
            print("🔑 Login: admin@avicenne.fr | Pass: admin123")
        except Exception as e:
            await session.rollback()
            print(f"❌ Erreur lors du commit final : {e}")

if __name__ == "__main__":
    asyncio.run(init_db())