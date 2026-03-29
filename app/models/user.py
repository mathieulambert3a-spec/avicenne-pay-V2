# app/models/user.py

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String, Boolean, DateTime, Enum as SAEnum, func,
    Table, Column, Integer, ForeignKey, Index, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref
from app.database import Base

if TYPE_CHECKING:
    from app.models.declaration import Declaration
    from app.models.sub_mission import SousMission
    from app.models.student import Student

# ── Raccourci pour values_callable ───────────────────────────────────────
_vc = lambda x: [e.value for e in x]  # noqa: E731

# ── Table de liaison permissions ──────────────────────────────────────────
user_sous_mission_permissions = Table(
    "user_sous_mission_permissions",
    Base.metadata,
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "sous_mission_id",
        Integer,
        ForeignKey("sous_missions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ── Enums métier ──────────────────────────────────────────────────────────

class Role(str, enum.Enum):
    admin   = "admin"
    coordo  = "coordo"
    resp    = "resp"
    tcp     = "tcp"
    top     = "top"
    top_com = "top_com"
    com     = "com"
    parrain_marraine = "parrain_marraine"

class Filiere(str, enum.Enum):
    medecine       = "Médecine"
    pharmacie      = "Pharmacie"
    maieutique     = "Maïeutique"
    odontologie    = "Odontologie"
    kinesitherapie = "Kinésithérapie"


class Annee(str, enum.Enum):
    p2 = "P2"
    d1 = "D1"
    d2 = "D2"


class Site(str, enum.Enum):
    lyon_est = "Lyon Est"
    lyon_sud = "Lyon Sud"


class Programme(str, enum.Enum):
    pass_ = "PASS"
    las1  = "LAS 1"
    las2  = "LAS 2"


# ── Référentiel des matières ──────────────────────────────────────────────

MATIERES = {
    "PASS": [
        "UE_1", "UE_2", "UE_3", "UE_4", "UE_5", "UE_6", "UE_7", "UE_8",
        "MMOK", "PHARMA",
        "Min SVE", "Min SVH", "Min SPS", "Min EEEA",
        "Min PHY_MECA", "Min MATH", "Min CHIMIE", "Min STAPS",
        "Min DROIT", "ORAUX",
    ],
    "LAS 1": [
        "Physiologie", "Anatomie", "Biologie Cell", "Biochimie",
        "Biostats", "Biophysique", "Chimie", "SSH",
        "Santé Publique", "ICM", "HBDV",
    ],
    "LAS 2": [
        "Microbiologie", "Biocell / Immuno", "Biologie Dev",
        "Enzmo / Métabo", "Génétique", "Physiologie",
        "Statistiques", "MES GSE",
    ],
}

# Rôles nécessitant un profil de paiement complet
ROLES_CONTRACTUELS = {
    Role.coordo, Role.resp, Role.tcp,
    Role.top, Role.top_com, Role.com,
}

# ── Modèle ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    # 1. AUTH : On autorise le vide pour les parrains sans accès
    id:              Mapped[int]  = mapped_column(primary_key=True)
    is_active:       Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email:           Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role:            Mapped[Role] = mapped_column(
        SAEnum(Role, name="role_enum", values_callable=_vc),
        nullable=False,
    )

    # 2. COORDONNÉES (Complétées)
    nom:        Mapped[str | None] = mapped_column(String(100))
    prenom:     Mapped[str | None] = mapped_column(String(100))
    telephone:  Mapped[str | None] = mapped_column(String(20))
    adresse:    Mapped[str | None] = mapped_column(String(255))
    code_postal:Mapped[str | None] = mapped_column(String(10))
    ville:      Mapped[str | None] = mapped_column(String(100))
    
    # Pour la paie / administration
    date_naissance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lieu_naissance: Mapped[str | None]      = mapped_column(String(100))

    # 3. --- HIÉRARCHIE ---
    manager_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relation vers le supérieur (ex: le TOP du Parrain)
    manager: Mapped["User | None"] = relationship(
        "User", 
        remote_side=[id], 
        back_populates="subordinates"
    )
    
    # Relation vers les subordonnés (ex: les Parrains du TOP)
    subordinates: Mapped[list["User"]] = relationship(
        "User", 
        back_populates="manager"
    )

   # 4. --- AJOUTS V3 : ÉTUDIANTS (P1) ---
    # On utilise une chaîne "Student" pour éviter l'erreur "not defined"
    students_mentored: Mapped[list["Student"]] = relationship("Student", back_populates="mentor")

    # 5 --- Données sensibles chiffrées
    nss_encrypted:  Mapped[str | None] = mapped_column(String(500))
    iban_encrypted: Mapped[str | None] = mapped_column(String(500))

    # Contexte pédagogique
    filiere:   Mapped[Filiere | None]   = mapped_column(
        SAEnum(Filiere, name="filiere_enum", values_callable=_vc)
    )
    annee:     Mapped[Annee | None]     = mapped_column(
        SAEnum(Annee, name="annee_enum", values_callable=_vc)
    )
    site:      Mapped[Site | None]      = mapped_column(
        SAEnum(Site, name="site_enum", values_callable=_vc)
    )
    programme: Mapped[Programme | None] = mapped_column(
        SAEnum(Programme, name="programme_enum", values_callable=_vc)
    )
    matiere:   Mapped[str | None]       = mapped_column(String(100))

    profil_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Métadonnées
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Contraintes d'unicité conditionnelles ─────────────────────────────
    __table_args__ = (
        # 1 seul RESP actif par site / programme / matière
        Index(
            "uq_resp_site_programme_matiere",
            "site", "programme", "matiere",
            unique=True,
            postgresql_where=text(
                "role = 'resp' AND is_active = true AND matiere IS NOT NULL"
            ),
        ),
        # 1 seul TOP COM actif par site
        Index(
            "uq_top_com_site",
            "site",
            unique=True,
            postgresql_where=text("role = 'top_com' AND is_active = true"),
        ),
    )

    # ── Propriétés métier ─────────────────────────────────────────────────

    @property
    def is_payment_profile_complete(self) -> bool:
        """Vérifie la présence des informations critiques pour le paiement."""
        champs = [
            self.nom, self.prenom, self.adresse,
            self.ville, self.nss_encrypted, self.iban_encrypted,
        ]
        return all(val and str(val).strip() for val in champs)

    def can_submit_declaration(self) -> bool:
        """
        Retourne True uniquement si :
        1. Le rôle est contractuel (pas admin)
        2. Le profil de paiement est complet
        """
        if self.role not in ROLES_CONTRACTUELS:
            return False
        return self.is_payment_profile_complete

    @property
    def role_label(self) -> str:
        """Libellé lisible pour les templates Jinja2."""
        return {
            Role.admin:   "Administrateur",
            Role.coordo:  "Coordinateur",
            Role.resp:    "Responsable de Matière",
            Role.tcp:     "TCP",
            Role.top:     "TOP",
            Role.top_com: "TOP Communication",
            Role.com:     "Communication",
        }.get(self.role, self.role.value)

       # ── Relations ─────────────────────────────────────────────────────────

    # Déclarations dont cet user est l'auteur
    declarations: Mapped[list["Declaration"]] = relationship(
        "Declaration",
        foreign_keys="[Declaration.user_id]",        # ← disambiguïté obligatoire
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Déclarations que cet user a validées (en tant qu'admin/coordo)
    declarations_validees: Mapped[list["Declaration"]] = relationship(
        "Declaration",
        foreign_keys="[Declaration.validee_par_id]", # ← 2ème FK
        back_populates="validee_par",
    )

    sous_missions_autorisees: Mapped[list["SousMission"]] = relationship(
        "SousMission",
        secondary=user_sous_mission_permissions,
        back_populates="utilisateurs_autorises",
    )

# ── Propriétés métier & Logique de validation ─────────────────────────

    @property
    def is_payment_profile_complete_logic(self) -> bool:
        """
        Vérifie techniquement si les infos critiques sont saisies.
        Sert à barrer les éléments dans l'alerte rouge du template.
        """
        champs_obligatoires = [
            self.nom, self.prenom, self.adresse,
            self.ville, self.nss_encrypted, self.iban_encrypted,
        ]
        # Retourne True si TOUS les champs sont remplis et non vides
        return all(val and str(val).strip() for val in champs_obligatoires)

    def can_submit_declaration(self) -> bool:
        """
        L'utilisateur ne peut déclarer que si :
        1. Son rôle est dans ROLES_CONTRACTUELS.
        2. Il a cliqué sur le bouton 'Valider' (colonne profil_complete = True).
        """
        if self.role not in ROLES_CONTRACTUELS:
            return False
        return self.profil_complete