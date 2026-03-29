# app/schemas/user.py

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from app.models.user import Role, Filiere, Annee, Site, Programme
from datetime import datetime


# ─────────────────────────────────────────────
# CONSTANTES MÉTIER (cohérence avec models/user.py)
# ─────────────────────────────────────────────

# Rôles qui doivent soumettre des déclarations (contrats)
# Ajout de parrain_marraine pour la V3
ROLES_CONTRACTUELS = {"coordo", "resp", "tcp", "top", "top_com", "com", "parrain_marraine"}

# Rôles avec contrat DA (Cession de Droits d'Auteur)
ROLES_DA = {"resp", "tcp"}

# Rôles avec contrat CDDU Pédagogique
ROLES_CDDU_PEDA = {"coordo", "top"}

# Rôles avec contrat CDDU Communication
ROLES_CDDU_COM = {"top_com", "com"}

# Rôles qui ne se connectent pas (pas d'email/password requis) - Spécifique V3
ROLES_SANS_ACCES = {"parrain_marraine"}


# ─────────────────────────────────────────────
# CRÉATION
# ─────────────────────────────────────────────

class UserCreate(BaseModel):
    """Création d'un utilisateur par l'admin."""
    nom: str # Obligatoire en V3 pour identifier les parrains/marraines
    prenom: str # Obligatoire en V3
    email: Optional[str] = None # Devient optionnel pour ROLES_SANS_ACCES
    password: Optional[str] = None # Devient optionnel pour ROLES_SANS_ACCES
    role: Role
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None
    
    # Lien hiérarchique (V3)
    manager_id: Optional[int] = None

    @field_validator("email", "password")
    @classmethod
    def credentials_required_unless_no_access(cls, v, info):
        role = info.data.get("role")
        role_str = role.value if hasattr(role, "value") else str(role)
        
        # Si le rôle n'est pas dans la liste sans accès, email/pass sont requis
        if role_str not in ROLES_SANS_ACCES and v is None:
            raise ValueError(f"L'email et le mot de passe sont obligatoires pour le rôle '{role_str}'.")
        return v

    @field_validator("site")
    @classmethod
    def site_required_for_contractuels(cls, v, info):
        role = info.data.get("role")
        role_str = role.value if hasattr(role, "value") else str(role)
        if role_str in ROLES_CONTRACTUELS and v is None:
            raise ValueError(f"Le site est obligatoire pour le rôle '{role_str}'.")
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
    # Hiérarchie (V3)
    manager_id: Optional[int] = None


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
    email: Optional[str] = None # Modifié car peut être null pour parrain/marraine
    role: Role
    is_active: bool
    manager_id: Optional[int] = None

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
    email: Optional[str] = None
    role: Role
    nom: Optional[str] = None
    prenom: Optional[str] = None
    site: Optional[Site] = None
    programme: Optional[Programme] = None
    matiere: Optional[str] = None
    manager_id: Optional[int] = None
    profil_complete: bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# HELPERS MÉTIER (utilisables dans les routes/services)
# ─────────────────────────────────────────────

def get_contract_type(role: Role) -> Optional[str]:
    """
    Retourne le type de contrat associé à un rôle.
    - 'DA'         : Cession de Droits d'Auteur
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

# ─────────────────────────────────────────────
# ÉTUDIANTS (P1 - Première Année Santé)
# ─────────────────────────────────────────────

class StudentCreate(BaseModel):
    """Création d'un étudiant P1 par un Admin, Coordo ou TOP COM."""
    nom: str
    prenom: str
    faculte: str  # "Lyon Sud" ou "Lyon Est"
    programme: Programme
    # Le parrain ou la marraine assigné(e)
    mentor_id: int 

class StudentUpdate(BaseModel):
    """Mise à jour des informations d'un étudiant P1."""
    nom: Optional[str] = None
    prenom: Optional[str] = None
    faculte: Optional[str] = None
    programme: Optional[Programme] = None
    mentor_id: Optional[int] = None

class StudentRead(BaseModel):
    """Lecture des données d'un étudiant (pour l'affichage)."""
    id: int
    nom: str
    prenom: str
    faculte: str
    programme: Programme
    mentor_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True