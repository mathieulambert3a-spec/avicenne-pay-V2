# app/models/__init__.py — ordre strict (dépendances d'abord)

from app.models.user import User, Site, Programme, Role         
from app.models.mission import Mission, TypeContrat             
from app.models.sub_mission import SousMission, UniteType        
from app.models.student import Student, Faculte                  
from app.models.declaration import (                             
    Declaration,
    LigneDeclaration,
    StatutDeclaration,
)

__all__ = [
    "User", "Site", "Programme", "Role",
    "Mission", "TypeContrat",
    "SousMission", "UniteType",
    "Student", "Faculte",                                        
    "Declaration", "LigneDeclaration", "StatutDeclaration",
]