# app/models/mission.py

from datetime import datetime
import enum
from sqlalchemy import String, Boolean, Integer, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.sub_mission import SousMission

from app.database import Base


class TypeContrat(str, enum.Enum):
    """
    Catégorise la mission pour le routing métier.

    Détermine :
      - le template affiché à l'utilisateur
      - le multiplicateur financier (DA → ×1.2)
      - les rôles autorisés à voir/saisir la mission
    """
    DA        = "DA"          # Cession Droits d'Auteur  → Resp, TCP
    CDDU_PEDA = "CDDU_PEDA"   # CDDU Pédagogique         → Coordo, TOP
    CDDU_COM  = "CDDU_COM"    # CDDU Communication       → TOP COM, COM

    @property
    def multiplicateur(self) -> float:
        """Multiplicateur financier appliqué au tarif de base."""
        return 1.2 if self == TypeContrat.DA else 1.0

    @property
    def label(self) -> str:
        """Libellé lisible pour les templates."""
        return {
            TypeContrat.DA:        "Cession Droits d'Auteur",
            TypeContrat.CDDU_PEDA: "CDDU Pédagogique",
            TypeContrat.CDDU_COM:  "CDDU Communication",
        }[self]


class Mission(Base):
    __tablename__ = "missions"

    id:    Mapped[int] = mapped_column(primary_key=True)
    titre: Mapped[str] = mapped_column(String(500), nullable=False)

    type_contrat: Mapped[TypeContrat] = mapped_column(
        SAEnum(
            TypeContrat,
            name="typecontrat_enum",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TypeContrat.DA,
        comment="DA | CDDU_PEDA | CDDU_COM",
    )

    ordre:     Mapped[int]  = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    resp_only: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Si True, seul un Responsable peut déclarer (quantité forcée à 1)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relations ─────────────────────────────────────────────────────────

    sous_missions: Mapped[list["SousMission"]] = relationship(
        "SousMission",
        back_populates="mission",
        order_by="SousMission.ordre",
        cascade="all, delete-orphan",
    )
