# app/schemas/user.py

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from app.models.user import Role, Filiere, Annee, Site, Programme
from datetime import datetime


# ─────────────────────────────────────────────
# CONSTANTES MÉTIER (cohérence avec models/user.py)
# ─────────────────────────────────────────────

# Rôles qui doivent soumettre des déclarations (contrats)
ROLES_CONTRACTUELS = {"coordo", "resp", "tcp", "top", "top_com", "com"}

# Rôles avec contrat DA (Cession de Droits d'Auteur)
ROLES_DA = {"resp", "tcp"}

# Rôles avec contrat CDDU Pédagogique
ROLES_CDDU_PEDA = {"coordo", "top"}

# Rôles avec contrat CDDU Communication
ROLES_CDDU_COM = {"top_com", "com"}


# ─────────────────────────────────────────────
# CRÉATION
# ─────────────────────────────────────────────

class UserCreate(BaseModel):
    """Création d'un utilisateur par l'admin."""
    email: str
    password: str
    role: Role
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None

    @field_validator("site")
    @classmethod
    def site_required_for_contractuels(cls, v, info):
        role = info.data.get("role")
        if role in ROLES_CONTRACTUELS and v is None:
            raise ValueError(f"Le site est obligatoire pour le rôle '{role}'.")
        return v


# ─────────────────────────────────────────────
# MISE À JOUR (par l'admin)
# ─────────────────────────────────────────────

class UserUpdate(BaseModel):
    """Mise à jour d'un utilisateur par l'admin."""
    email: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    nom: Optional[str] = None
    prenom: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    telephone: Optional[str] = None
    # Données sensibles : transmises en clair, chiffrées côté service
    nss: Optional[str] = None
    iban: Optional[str] = None
    # Affectation métier
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None
    filiere: Optional[Filiere] = None
    annee: Optional[Annee] = None


# ─────────────────────────────────────────────
# MISE À JOUR DU PROFIL (par l'utilisateur lui-même)
# ─────────────────────────────────────────────

class UserProfileUpdate(BaseModel):
    """
    Champs que l'utilisateur peut modifier lui-même.
    Les données sensibles (NSS, IBAN) sont chiffrées côté service.
    """
    nom: Optional[str] = None
    prenom: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    telephone: Optional[str] = None
    nss: Optional[str] = None    # transmis en clair → chiffré en base
    iban: Optional[str] = None   # transmis en clair → chiffré en base


# ─────────────────────────────────────────────
# LECTURE (réponse API)
# ─────────────────────────────────────────────

class UserRead(BaseModel):
    """
    Représentation publique d'un utilisateur.
    Les données sensibles (NSS, IBAN) ne sont jamais exposées.
    """
    id: int
    email: str
    role: Role
    is_active: bool

    # Identité
    nom: Optional[str] = None
    prenom: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    telephone: Optional[str] = None

    # Affectation métier
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None
    filiere: Optional[Filiere] = None
    annee: Optional[Annee] = None

    # Statut
    profil_complete: bool
    created_at: datetime
    updated_at: datetime

    # ⚠️ nss_encrypted et iban_encrypted ne sont JAMAIS exposés

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# LECTURE RÉSUMÉE (listes, dropdowns)
# ─────────────────────────────────────────────

class UserSummary(BaseModel):
    """
    Version allégée pour les listes et les sélecteurs.
    Ex: liste des TCPs d'un Resp, liste des COMs d'un TOP COM.
    """
    id: int
    email: str
    role: Role
    nom: Optional[str] = None
    prenom: Optional[str] = None
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None
    profil_complete: bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# HELPERS MÉTIER (utilisables dans les routes/services)
# ─────────────────────────────────────────────

def get_contract_type(role: Role) -> Optional[str]:
    """
    Retourne le type de contrat associé à un rôle.
    - 'DA'        : Cession de Droits d'Auteur
    - 'CDDU_PEDA' : CDDU Pédagogique
    - 'CDDU_COM'  : CDDU Communication
    - None        : Admin (CDI, pas de déclaration)
    """
    role_str = role.value if hasattr(role, "value") else str(role)
    if role_str in ROLES_DA:
        return "DA"
    if role_str in ROLES_CDDU_PEDA:
        return "CDDU_PEDA"
    if role_str in ROLES_CDDU_COM:
        return "CDDU_COM"
    return None  # admin


def get_template_for_role(role: Role) -> Optional[str]:
    """
    Retourne le nom du template de déclaration associé à un rôle.
    """
    role_str = role.value if hasattr(role, "value") else str(role)
    if role_str in ROLES_DA:
        return "missions_da.html"
    if role_str in ROLES_CDDU_PEDA:
        return "missions_peda.html"
    if role_str in ROLES_CDDU_COM:
        return "missions_com.html"
    return None
