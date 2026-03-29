# app/models/__init__.py — ordre strict (dépendances d'abord)

from app.models.user import User, Site, Programme, Role          # 1 — crée site_enum, programme_enum
from app.models.mission import Mission, TypeContrat              # 2 — crée typecontrat_enum
from app.models.sub_mission import SousMission, UniteType        # 3 — crée unitetype_enum
from app.models.declaration import (                             # 4 — réutilise site_enum, programme_enum
    Declaration,
    LigneDeclaration,
    StatutDeclaration,
)

__all__ = [
    "User", "Site", "Programme", "Role",
    "Mission", "TypeContrat",
    "SousMission", "UniteType",
    "Declaration", "LigneDeclaration", "StatutDeclaration",
]
