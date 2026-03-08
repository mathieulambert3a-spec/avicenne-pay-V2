import os
import sys
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.schemas.constants import MISSIONS_INITIALES


async def main():
    async with AsyncSessionLocal() as db:
        # Missions existantes indexées par titre
        res = await db.execute(select(Mission))
        existing_missions = {m.titre: m for m in res.scalars().all()}

        created_m = updated_m = created_sm = updated_sm = 0

        for mission_titre, sous_missions in MISSIONS_INITIALES.items():
            mission = existing_missions.get(mission_titre)

            if mission is None:
                mission = Mission(titre=mission_titre, ordre=0, is_active=True)
                db.add(mission)
                await db.flush()  # mission.id dispo
                existing_missions[mission_titre] = mission
                created_m += 1
            else:
                if not mission.is_active:
                    mission.is_active = True
                    updated_m += 1

            # IMPORTANT: requête explicite des sous-missions (pas de mission.sous_missions)
            res_sms = await db.execute(
                select(SousMission).where(SousMission.mission_id == mission.id)
            )
            sms = res_sms.scalars().all()
            existing_sms = {sm.titre: sm for sm in sms}

            for idx, sm_def in enumerate(sous_missions):
                sm_titre = sm_def["titre"].strip()
                new_tarif = float(sm_def["tarif"])
                new_unite = sm_def.get("unite")

                sm = existing_sms.get(sm_titre)
                if sm is None:
                    sm = SousMission(
                        mission_id=mission.id,
                        titre=sm_titre,
                        tarif=new_tarif,
                        unite=new_unite,
                        ordre=idx,
                        is_active=True,
                    )
                    db.add(sm)
                    created_sm += 1
                else:
                    changed = False
                    if sm.tarif != new_tarif:
                        sm.tarif = new_tarif
                        changed = True
                    if (sm.unite or None) != (new_unite or None):
                        sm.unite = new_unite
                        changed = True
                    if sm.ordre != idx:
                        sm.ordre = idx
                        changed = True
                    if not sm.is_active:
                        sm.is_active = True
                        changed = True
                    if changed:
                        updated_sm += 1

        await db.commit()

    print(
        "✅ Seed missions terminé. "
        f"Missions: +{created_m} / ~{updated_m}. "
        f"Sous-missions: +{created_sm} / ~{updated_sm}."
    )


if __name__ == "__main__":
    asyncio.run(main())