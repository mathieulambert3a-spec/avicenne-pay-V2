from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, case
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from passlib.context import CryptContext
from typing import Optional, List

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, Role, Site, Programme, MATIERES
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.common.templates import templates

router = APIRouter(prefix="/users")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("", response_class=HTMLResponse)
async def list_users(   
    request: Request, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. DÉFINITION DE LA HIÉRARCHIE DES RÔLES (Tri pour l'affichage)
    role_priority = case(
        {
            Role.admin: 1,
            Role.coordo: 2,
            Role.top_com: 3,
            Role.top: 4,
            Role.resp: 5,
            Role.tcp: 6,
            Role.parrain_marraine: 7, # Placé après les rôles pédagogiques
            Role.com: 8,
        },
        value=User.role,
        else_=9
    )

    # 2. PRÉPARATION DE LA REQUÊTE
    query = (
        select(User)
        .options(selectinload(User.manager)) 
        .order_by(role_priority, User.nom.asc(), User.prenom.asc())
    )
    
    # 3. FILTRES DE SÉCURITÉ ET VISIBILITÉ DES PARRAINS
    
    if current_user.role == Role.admin:
        # L'Admin voit l'intégralité de la base, parrains inclus.
        pass 
        
    elif current_user.role == Role.coordo:
        # Le Coordo voit tout son site (Staff + Parrains rattachés à son site)
        query = query.where(User.site == current_user.site)
        
    elif current_user.role == Role.top:
        # Le TOP voit uniquement les Parrains/Marraines qu'il a créés (manager_id)
        # Il ne voit pas les autres membres du staff.
        query = query.where(
            User.manager_id == current_user.id,
            User.role == Role.parrain_marraine
        )
        
    elif current_user.role == Role.top_com:
        # Le TOP COM ne voit que les COM de son site (Pas de parrains)
        query = query.where(
            User.site == current_user.site,
            User.role == Role.com
        )
        
    elif current_user.role == Role.resp:
        # Le RESP voit ses TCP sur son site/matière (Pas de parrains)
        query = query.where(
            User.role == Role.tcp,
            User.site == current_user.site,
            User.matiere == current_user.matiere
        )
        
    else: 
        # Sécurité pour TCP, COM et Parrains : vision restreinte à soi-même
        query = query.where(User.id == current_user.id)

    # 4. EXÉCUTION
    result = await db.execute(query)
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "admin/users.html", 
        {
            "request": request, 
            "users": users, 
            "current_user": current_user, 
            "user": current_user, 
            "roles": list(Role),
            "sites": list(Site),
            "programmes": list(Programme),
            "matieres_par_prog": MATIERES
        }
    )
# --- AFFICHER LE FORMULAIRE DE PERMISSIONS ---
@router.get("/{user_id}/permissions", response_class=HTMLResponse)
async def get_user_permissions(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Récupérer l'utilisateur cible
    res = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.missions_autorisees))
    )
    target_user = res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # --- Bloquer si c'est un coordinateur ---
    if target_user.role == Role.coordo:
        raise HTTPException(
            status_code=400, 
            detail="Les coordinateurs n'ont pas de déclarations à paramétrer."
        )

    # 2. Vérification des droits d'accès
    allowed = False
    if current_user.role == Role.admin:
        allowed = True
    elif current_user.role == Role.coordo:
        allowed = (target_user.site == current_user.site)
    elif current_user.role == Role.resp:
        allowed = (target_user.role == Role.tcp and target_user.site == current_user.site and target_user.matiere == current_user.matiere)

    if not allowed:
        raise HTTPException(status_code=403, detail="Accès refusé à ce périmètre.")

    # 3. Récupérer le catalogue complet des missions
    missions_res = await db.execute(
        select(Mission).options(selectinload(Mission.sous_missions)).order_by(Mission.ordre)
    )
    all_missions = missions_res.scalars().all()

    # 4. Préparer les IDs déjà cochés
    current_permissions_ids = [sm.id for sm in target_user.missions_autorisees]

    return templates.TemplateResponse(
        "user_permissions.html",
        {
            "request": request,
            "target_user": target_user,
            "all_missions": all_missions,
            "current_permissions_ids": current_permissions_ids,
            "current_user": current_user
        }
    )

# --- ENREGISTRER LES PERMISSIONS ---
@router.post("/{user_id}/permissions")
async def update_user_permissions(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Récupérer les données du formulaire
    form_data = await request.form()
    sous_mission_ids = form_data.getlist("sous_mission_ids")
    
    try:
        sous_mission_ids = [int(sid) for sid in sous_mission_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Identifiants de missions invalides.")

    # 2. Récupérer l'utilisateur cible
    res = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.missions_autorisees))
    )
    target_user = res.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # --- 2.5 RÈGLE MÉTIER : Pas de missions pour les coordinateurs ---
    if target_user.role == Role.coordo:
        raise HTTPException(
            status_code=400, 
            detail="Les coordinateurs ne remplissent pas de déclarations."
        )

    # 3. SÉCURITÉ : Vérification des droits (votre code existant)
    allowed = False
    if current_user.role == Role.admin:
        allowed = True
    elif current_user.role == Role.coordo:
        allowed = (target_user.site == current_user.site)
    elif current_user.role == Role.resp:
        allowed = (
            target_user.role == Role.tcp and 
            target_user.site == current_user.site and 
            target_user.matiere == current_user.matiere
        )

    if not allowed:
        raise HTTPException(status_code=403, detail="Opération non autorisée.")

    # 4. MISE À JOUR
    if sous_mission_ids:
        sm_res = await db.execute(
            select(SousMission).where(SousMission.id.in_(sous_mission_ids))
        )
        target_user.missions_autorisees = list(sm_res.scalars().all())
    else:
        target_user.missions_autorisees = []

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Erreur : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement.")

    return RedirectResponse(url="/users", status_code=303)

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    password: Optional[str] = Form(None),
    role: str = Form(...),
    nom: str = Form(""),       
    prenom: str = Form(""), 
    telephone: Optional[str] = Form(None),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        target_role = Role(role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Rôle invalide")

    # --- INITIALISATION DES VARIABLES ---
    new_user_site = None
    new_user_prog = None
    new_user_matiere = None
    new_user_manager_id = None
    is_profil_complete = False 

    # --- 1. LOGIQUE MÉTIER ET HIÉRARCHIE ---
    
    if current_user.role == Role.admin:
        if site and site.strip(): 
            new_user_site = Site(site)
        
        if target_role in [Role.resp, Role.tcp, Role.top, Role.parrain_marraine]:
            if programme and programme.strip():
                new_user_prog = Programme(programme)
            
            if target_role in [Role.resp, Role.tcp]:
                new_user_matiere = matiere if matiere and matiere.strip() else None

    elif current_user.role == Role.coordo:
        if target_role not in [Role.resp, Role.tcp, Role.top, Role.top_com, Role.com]:
            raise HTTPException(status_code=403, detail="Vous ne pouvez pas créer ce type de rôle.")
        
        new_user_site = current_user.site 
        if programme and programme.strip():
            new_user_prog = Programme(programme)
        new_user_matiere = matiere

    elif current_user.role == Role.resp:
        if target_role != Role.tcp:
            raise HTTPException(status_code=403, detail="Un Responsable ne peut créer que des TCP.")
        
        new_user_site = current_user.site
        new_user_prog = current_user.programme
        new_user_matiere = current_user.matiere
        new_user_manager_id = current_user.id

    elif current_user.role == Role.top:
        if target_role != Role.parrain_marraine:
            raise HTTPException(status_code=403, detail="Un TOP ne peut créer que des Parrains/Marraines.")
        
        new_user_site = current_user.site
        new_user_prog = current_user.programme 
        new_user_manager_id = current_user.id
        
        # Le parrain est créé avec son identité complète par le TOP
        is_profil_complete = True 

    # --- 2. GESTION DU MOT DE PASSE ---
    # Pour les parrains (pas d'accès), on génère un hash de sécurité aléatoire
    if target_role == Role.parrain_marraine:
        import secrets
        hashed_pw = pwd_context.hash(secrets.token_urlsafe(32))
    else:
        if not password:
            raise HTTPException(status_code=400, detail="Le mot de passe est obligatoire.")
        hashed_pw = pwd_context.hash(password)

    # --- 3. VÉRIFICATION D'EXISTENCE ---
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/admin/users?error=email_exists", status_code=303)

    # --- 4. CRÉATION DE L'UTILISATEUR ---
    new_user = User(
        email=email.lower().strip(),
        nom=nom.upper().strip() if nom else None,
        prenom=prenom.capitalize().strip() if prenom else None,
        telephone=telephone.strip() if telephone else None,
        hashed_password=hashed_pw,
        role=target_role,
        site=new_user_site,
        programme=new_user_prog, 
        matiere=new_user_matiere,
        manager_id=new_user_manager_id,
        profil_complete=is_profil_complete,
        is_active=True
    )

    db.add(new_user)
    
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Erreur lors de la création : {e}")
        raise HTTPException(status_code=500, detail="Erreur technique lors de l'enregistrement.")

    return RedirectResponse(url="/admin/users?msg=created", status_code=303)

@router.post("/{user_id}/delete")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user_to_delete = result.scalar_one_or_none()

    if not user_to_delete or user_to_delete.id == current_user.id:
        raise HTTPException(status_code=403)

    await db.delete(user_to_delete)
    await db.commit()
    return RedirectResponse(url="/users", status_code=303)

@router.post("/{user_id}/edit")
async def update_user(
    user_id: int,
    role: str = Form(...),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Récupération de l'utilisateur
    res = await db.execute(select(User).where(User.id == user_id))
    target_user = res.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # 2. Sécurité : On vérifie les droits (Admin ou Coordo du même site, etc.)
    # (Garde ta logique de vérification ici)

    # 3. Mise à jour des seuls champs modifiables
    try:
        target_user.role = Role(role)
        target_user.site = Site(site) if site and site.strip() else None
        target_user.programme = Programme(programme) if programme and programme.strip() else None
        target_user.matiere = matiere if matiere and matiere.strip() else None

        # Règle : Si Admin, pas d'affectation spécifique
        if target_user.role == Role.admin:
            target_user.site = None
            target_user.programme = None
            target_user.matiere = None

        await db.commit()
        return RedirectResponse(url="/admin/users?msg=updated", status_code=303)

    except IntegrityError:
        await db.rollback()
        # Redirection avec l'erreur de doublon RESP
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=duplicate_resp", status_code=303)