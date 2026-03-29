# app/models/sub_mission.py

from datetime import datetime
import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, Boolean, Integer, Float,
    ForeignKey, DateTime, func, Enum as SAEnum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import user_sous_mission_permissions

if TYPE_CHECKING:
    from app.models.mission import Mission
    from app.models.declaration import LigneDeclaration
    from app.models.user import User

# ── Raccourci values_callable ─────────────────────────────────────────────
_vc = lambda x: [e.value for e in x]  # noqa: E731


# ── Enum métier ───────────────────────────────────────────────────────────

class UniteType(str, enum.Enum):
    HEURE     = "heure"
    FORFAIT   = "forfait"
    JOURNEE   = "journée"
    DEMI_JOUR = "demi-journée"
    ETUDIANT  = "étudiant"


# ── Modèle ────────────────────────────────────────────────────────────────

class SousMission(Base):
    __tablename__ = "sous_missions"

    id:         Mapped[int]  = mapped_column(primary_key=True)
    mission_id: Mapped[int]  = mapped_column(
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
    )

    titre: Mapped[str]   = mapped_column(String(500), nullable=False)
    tarif: Mapped[float] = mapped_column(Float,       nullable=False)

    unite: Mapped[UniteType] = mapped_column(
        SAEnum(UniteType, name="unitetype_enum", values_callable=_vc),
        nullable=False,
        default=UniteType.FORFAIT,
    )

    ordre:     Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_active: Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Contraintes ───────────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("tarif >= 0", name="ck_sous_mission_tarif_positif"),
    )

    # ── Propriétés métier ─────────────────────────────────────────────────

    @property
    def unite_label(self) -> str:
        """Libellé capitalisé pour les templates Jinja2."""
        return {
            UniteType.HEURE:     "Heure",
            UniteType.FORFAIT:   "Forfait",
            UniteType.JOURNEE:   "Journée",
            UniteType.DEMI_JOUR: "Demi-journée",
            UniteType.ETUDIANT:  "Étudiant",
        }.get(self.unite, self.unite.value.capitalize())

    def __repr__(self) -> str:
        return (
            f"<SousMission id={self.id} "
            f"titre={self.titre!r} "
            f"tarif={self.tarif} "
            f"unite={self.unite.value}>"
        )

    # ── Relations ─────────────────────────────────────────────────────────

    mission: Mapped["Mission"] = relationship(
        "Mission",
        back_populates="sous_missions",
    )

    lignes: Mapped[list["LigneDeclaration"]] = relationship(
        "LigneDeclaration",
        back_populates="sous_mission",
        cascade="all, delete-orphan",
    )

    utilisateurs_autorises: Mapped[list["User"]] = relationship(
        "User",
        secondary=user_sous_mission_permissions,
        back_populates="sous_missions_autorisees",
    )
