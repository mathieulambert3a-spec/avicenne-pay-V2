# app/models/declaration.py

import enum
from datetime import datetime
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING

from sqlalchemy import (
    Integer, ForeignKey, DateTime, Enum as SAEnum,
    func, String, Float, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import Site, Programme

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.sub_mission import SousMission

_vc = lambda x: [e.value for e in x]  # noqa: E731


class StatutDeclaration(str, enum.Enum):
    brouillon         = "brouillon"
    soumise           = "soumise"
    validee           = "validee"
    validation_finale = "validation_finale"


class Declaration(Base):
    __tablename__ = "declarations"

    id:      Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    validee_par_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    site: Mapped[Site] = mapped_column(
        SAEnum(Site, name="site_enum", create_type=False, values_callable=_vc),
        nullable=False,
    )
    programme: Mapped[Programme] = mapped_column(
        SAEnum(Programme, name="programme_enum", create_type=False, values_callable=_vc),
        nullable=False,
    )

    mois:  Mapped[int] = mapped_column(Integer, nullable=False)
    annee: Mapped[int] = mapped_column(Integer, nullable=False)

    statut: Mapped[StatutDeclaration] = mapped_column(
        SAEnum(StatutDeclaration, name="statutdeclaration_enum", values_callable=_vc),
        default=StatutDeclaration.brouillon,
        nullable=False,
    )

    commentaire_admin: Mapped[str | None] = mapped_column(String(500))

    soumise_le:           Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validee_le:           Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_finale_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("mois >= 1 AND mois <= 12",        name="ck_declaration_mois_valide"),
        CheckConstraint("annee >= 2020 AND annee <= 2100", name="ck_declaration_annee_valide"),
        UniqueConstraint(
            "user_id", "site", "programme", "mois", "annee",
            name="uq_declaration_user_periode",
        ),
    )

    # ── Relations ────────────────────────────────────────────────────────
    # ✅ foreign_keys en liste — sans ambiguïté
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys="[Declaration.user_id]",       # ← crochets obligatoires en string
        back_populates="declarations",
    )
    validee_par: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[Declaration.validee_par_id]", # ← crochets obligatoires en string
        back_populates="declarations_validees",       # ← back_populates, pas overlaps
    )
    lignes: Mapped[list["LigneDeclaration"]] = relationship(
        "LigneDeclaration",
        back_populates="declaration",
        cascade="all, delete-orphan",
    )


class LigneDeclaration(Base):
    __tablename__ = "lignes_declaration"

    id:             Mapped[int] = mapped_column(primary_key=True)
    declaration_id: Mapped[int] = mapped_column(
        ForeignKey("declarations.id", ondelete="CASCADE"), nullable=False
    )
    sous_mission_id: Mapped[int] = mapped_column(
        ForeignKey("sous_missions.id"), nullable=False
    )

    quantite:        Mapped[float]        = mapped_column(Float, nullable=False)
    montant_calcule: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint("quantite > 0", name="ck_ligne_quantite_positive"),
    )

    declaration: Mapped["Declaration"] = relationship(
        "Declaration",
        back_populates="lignes",
    )
    sous_mission: Mapped["SousMission"] = relationship(
        "SousMission",
        back_populates="lignes",
    )
