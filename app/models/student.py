# app/models/student.py

# app/models/student.py

import enum
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# On récupère l'Enum Programme pour rester cohérent avec User
from app.models.user import Programme

class Faculte(str, enum.Enum):
    lyon_est = "Lyon Est"
    lyon_sud = "Lyon Sud"

class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    prenom: Mapped[str] = mapped_column(String(100), nullable=False)
    
    faculte: Mapped[Faculte] = mapped_column(
        SAEnum(Faculte, name="faculte_enum"), 
        nullable=False
    )
    
    programme: Mapped[Programme] = mapped_column(
        SAEnum(Programme, name="programme_enum_student"), 
        nullable=False
    )

    # ─────────────────────────────────────────────
    # RELATION : Mentorat (Lien vers User)
    # ─────────────────────────────────────────────
    mentor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Lien vers l'objet User (Parrain, TCP, etc.)
    mentor = relationship("User", back_populates="students_mentored")

    # Métadonnées
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )