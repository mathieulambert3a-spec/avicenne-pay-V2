# app/schemas/mission.py

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from enum import Enum


# ─────────────────────────────────────────────
# ENUMS MÉTIER
# ─────────────────────────────────────────────

class TypeContrat(str, Enum):
    """Type de contrat associé à une mission."""
    DA        = "DA"          # Cession de Droits d'Auteur (Resp, TCP)
    CDDU_PEDA = "CDDU_PEDA"   # CDDU Pédagogique (Coordo, TOP)
    CDDU_COM  = "CDDU_COM"    # CDDU Communication (TOP COM, COM)


class UniteType(str, Enum):
    """Unité de mesure pour le tarif d'une sous-mission."""
    HEURE      = "heure"
    FORFAIT    = "forfait"
    JOURNEE    = "journée"
    DEMI_JOUR  = "demi-journée"
    ETUDIANT   = "étudiant"   # ex: parrainage × nb étudiants


# ─────────────────────────────────────────────
# MISSION (niveau supérieur)
# ─────────────────────────────────────────────

class MissionCreate(BaseModel):
    """Création d'une mission par l'admin."""
    titre: str
    type_contrat: TypeContrat
    ordre: int = 0
    is_active: bool = True

    @field_validator("titre")
    @classmethod
    def titre_non_vide(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le titre ne peut pas être vide.")
        return v.strip()


class MissionUpdate(BaseModel):
    """Mise à jour partielle d'une mission."""
    titre: Optional[str] = None
    type_contrat: Optional[TypeContrat] = None
    ordre: Optional[int] = None
    is_active: Optional[bool] = None


class MissionRead(BaseModel):
    """Lecture d'une mission avec ses sous-missions."""
    id: int
    titre: str
    type_contrat: TypeContrat
    ordre: int
    is_active: bool
    sous_missions: List["SousMissionRead"] = []

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# SOUS-MISSION
# ─────────────────────────────────────────────

class SousMissionCreate(BaseModel):
    """Création d'une sous-mission rattachée à une mission."""
    mission_id: int
    titre: str
    tarif: float
    unite: UniteType = UniteType.FORFAIT
    ordre: int = 0
    is_active: bool = True

    @field_validator("titre")
    @classmethod
    def titre_non_vide(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le titre ne peut pas être vide.")
        return v.strip()

    @field_validator("tarif")
    @classmethod
    def tarif_positif(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Le tarif ne peut pas être négatif.")
        return v


class SousMissionUpdate(BaseModel):
    """Mise à jour partielle d'une sous-mission."""
    titre: Optional[str] = None
    tarif: Optional[float] = None
    unite: Optional[UniteType] = None
    ordre: Optional[int] = None
    is_active: Optional[bool] = None


class SousMissionRead(BaseModel):
    """
    Lecture d'une sous-mission.
    Inclut un flag 'est_autorisee' calculé selon les permissions
    de l'utilisateur connecté (injecté côté service/route).
    """
    id: int
    mission_id: int
    titre: str
    tarif: float
    unite: UniteType
    ordre: int
    is_active: bool
    est_autorisee: bool = True   # False si l'user n'a pas la permission

    class Config:
        from_attributes = True


# Résolution de la référence circulaire MissionRead → SousMissionRead
MissionRead.model_rebuild()


# ─────────────────────────────────────────────
# PERMISSIONS SUR SOUS-MISSIONS
# ─────────────────────────────────────────────

class UserSousMissionPermissionCreate(BaseModel):
    """
    Accorde à un utilisateur le droit de déclarer une sous-mission.
    Géré par l'admin ou le N+1 selon le rôle.
    """
    user_id: int
    sous_mission_id: int


class UserSousMissionPermissionRead(BaseModel):
    """Lecture d'une permission sous-mission."""
    user_id: int
    sous_mission_id: int
    sous_mission: Optional[SousMissionRead] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LIGNES DE DÉCLARATION
# ─────────────────────────────────────────────

class LigneDeclarationCreate(BaseModel):
    """
    Création d'une ligne dans une déclaration.
    La quantité est validée selon l'unité (ex: pas de 0.3 heure).
    """
    sous_mission_id: int
    quantite: float
    commentaire: Optional[str] = None

    @field_validator("quantite")
    @classmethod
    def quantite_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("La quantité doit être supérieure à 0.")
        return v


class LigneDeclarationUpdate(BaseModel):
    """Modification d'une ligne (avant soumission uniquement)."""
    quantite: Optional[float] = None
    commentaire: Optional[str] = None

    @field_validator("quantite")
    @classmethod
    def quantite_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("La quantité doit être supérieure à 0.")
        return v


class LigneDeclarationRead(BaseModel):
    """
    Lecture d'une ligne de déclaration.
    Le montant est calculé : tarif × quantite (× 1.2 si DA).
    """
    id: int
    declaration_id: int
    sous_mission_id: int
    quantite: float
    montant: float              # calculé côté service
    commentaire: Optional[str] = None
    sous_mission: Optional[SousMissionRead] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# RÉCAPITULATIF DÉCLARATION (helper lecture)
# ─────────────────────────────────────────────

class DeclarationRecap(BaseModel):
    """
    Résumé financier d'une déclaration.
    Calculé côté service, jamais stocké en base.
    """
    total_brut: float           # somme des montants avant multiplicateur
    multiplicateur: float       # 1.2 si DA, 1.0 sinon
    total_net: float            # total_brut × multiplicateur
    nb_lignes: int
    lignes: List[LigneDeclarationRead] = []
