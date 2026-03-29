from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload  # Indispensable pour l'asynchrone
from typing import Optional

from app.database import get_db
from app.dependencies import require_role
from app.models.user import Role
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration
from app.schemas.constants import UNITES_CHOICES
from app.common.templates import templates

router = APIRouter(prefix="/admin/referentiel/missions")

# Sécurité : Seuls Admin et Coordo accèdent à ces routes
can_manage_missions = require_role([Role.admin, Role.coordo])

# --- SECTION MISSIONS (PARENTS) ---
@router.get("/new", response_class=HTMLResponse)
async def new_mission_form(request: Request, current_user=Depends(can_manage_missions)):
    """Formulaire de création d'une nouvelle mission."""
    return templates.TemplateResponse(
        "missions/form.html", 
        {"request": request, "user": current_user, "mission": None}
    )


@router.post("/new")
async def create_mission(
    titre: str = Form(...),
    ordre: int = Form(0),
    is_active: str = Form("off"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Enregistre une nouvelle mission."""
    mission = Mission(
        titre=titre.strip(), 
        ordre=ordre, 
        is_active=(is_active == "on")
    )
    db.add(mission)
    await db.commit()
    return RedirectResponse("/admin/referentiel/missions", status_code=302)


@router.get("/{mission_id}/edit", response_class=HTMLResponse)
async def edit_mission_form(
    request: Request,
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    
    """Édite une mission (charge les sous-missions pour éviter l'erreur Greenlet)."""
    result = await db.execute(
        select(Mission)
        .where(Mission.id == mission_id)
        .options(selectinload(Mission.sous_missions))
    )
    mission = result.scalar_one_or_none()
    
    if not mission:
        return RedirectResponse("/admin/referentiel/missions", status_code=302)
        
    return templates.TemplateResponse(
        "missions/form.html", 
        {"request": request, "user": current_user, "mission": mission}
    )


@router.post("/{mission_id}/edit")
async def update_mission(
    mission_id: int,
    titre: str = Form(...),
    ordre: int = Form(0),
    is_active: str = Form("off"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Met à jour les infos de base d'une mission."""
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    
    if mission:
        mission.titre = titre.strip()
        mission.ordre = ordre
        mission.is_active = (is_active == "on")
        await db.commit()
        
    return RedirectResponse("/admin/referentiel/missions", status_code=302)


@router.post("/{mission_id}/delete", name="delete_mission")
async def delete_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    
    if mission:
        # Vérification si la mission est utilisée dans des déclarations existantes
        subq = select(SousMission.id).where(SousMission.mission_id == mission_id)
        query = select(LigneDeclaration).where(LigneDeclaration.sous_mission_id.in_(subq))
        line_check = await db.execute(query)
        
        if line_check.scalars().first():
            # CAS HISTORIQUE : On ne peut pas supprimer, donc on cache (Soft Delete)
            mission.is_active = False
            # Optionnel : Tu pourrais ici rediriger avec un paramètre ?msg=used
        else:
            # CAS VIERGE : On supprime vraiment de la base
            await db.delete(mission)
        
        await db.commit()
    
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)


# --- SECTION SOUS-MISSIONS (ENFANTS) ---

@router.get("/{mission_id}/sous-missions/new", response_class=HTMLResponse)
async def new_sub_mission_form(
    request: Request,
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Formulaire pour ajouter une sous-mission à une mission parente."""
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    
    return templates.TemplateResponse(
        "missions/sub_mission_form.html",
        {
            "request": request, 
            "user": current_user, 
            "mission": mission, 
            "sous_mission": None,
            "unites_disponibles": UNITES_CHOICES
        },
    )

@router.post("/{mission_id}/sous-missions/new")
async def create_sub_mission(
    mission_id: int,
    titre: str = Form(...),
    tarif: float = Form(...),
    unite: str = Form(""),
    ordre: int = Form(0),
    is_active: str = Form("off"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Crée une sous-mission liée."""
    sm = SousMission(
        mission_id=mission_id,
        titre=titre.strip(),
        tarif=tarif,
        unite=unite.strip() if unite else None,
        ordre=ordre,
        is_active=(is_active == "on"),
    )
    db.add(sm)
    await db.commit()
    return RedirectResponse("/admin/referentiel/missions", status_code=302)


@router.get("/{mission_id}/sous-missions/{sm_id}/edit", response_class=HTMLResponse)
async def edit_sub_mission_form(
    request: Request,
    mission_id: int,
    sm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Édition d'une sous-mission spécifique."""
    res_m = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = res_m.scalar_one_or_none()
    
    res_sm = await db.execute(select(SousMission).where(SousMission.id == sm_id))
    sous_mission = res_sm.scalar_one_or_none()
    
    return templates.TemplateResponse(
        "missions/sub_mission_form.html",
        {
            "request": request, 
            "user": current_user, 
            "mission": mission, 
            "sous_mission": sous_mission,
            "unites_disponibles": UNITES_CHOICES
        },
    )


@router.post("/{mission_id}/sous-missions/{sm_id}/edit")
async def update_sub_mission(
    sm_id: int,
    titre: str = Form(...),
    tarif: float = Form(...),
    unite: str = Form(""),
    ordre: int = Form(0),
    is_active: str = Form("off"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    """Met à jour les tarifs ou intitulés d'une sous-mission."""
    result = await db.execute(select(SousMission).where(SousMission.id == sm_id))
    sm = result.scalar_one_or_none()
    
    if sm:
        sm.titre = titre.strip()
        sm.tarif = tarif
        sm.unite = unite.strip() if unite else None
        sm.ordre = ordre
        sm.is_active = (is_active == "on")
        await db.commit()
        
    return RedirectResponse("/admin/referentiel/missions", status_code=302)


@router.post("/{mission_id}/sous-missions/{sm_id}/delete", name="delete_sub_mission")
async def delete_sub_mission(
    mission_id: int,
    sm_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(can_manage_missions),
):
    result = await db.execute(select(SousMission).where(SousMission.id == sm_id))
    sm = result.scalar_one_or_none()
    
    if sm:
        query = select(LigneDeclaration).where(LigneDeclaration.sous_mission_id == sm_id)
        line_check = await db.execute(query)
        
        if line_check.scalars().first():
            sm.is_active = False
        else:
            await db.delete(sm)
        await db.commit()
            
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

@router.get("/", response_class=HTMLResponse)
async def list_missions(
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user=Depends(can_manage_missions)
):
    # On utilise selectinload pour charger les enfants en une seule requête
    # On trie par 'ordre' pour respecter ton catalogue initial
    result = await db.execute(
        select(Mission)
        .options(selectinload(Mission.sous_missions))
        .order_by(Mission.ordre.asc()) 
    )
    missions = result.scalars().all()
    
    return templates.TemplateResponse(
        "missions_da.html",
        {
            "request": request, 
            "user": current_user, 
            "missions": missions,
            "unites_disponibles": UNITES_CHOICES
        }
    )