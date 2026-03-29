from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete
from sqlalchemy.orm import selectinload
from datetime import date
from typing import Optional, List

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, Role, Site
from app.models.mission import Mission
from app.models.sub_mission import SousMission
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
from app.common.templates import templates

router = APIRouter()


MOIS_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

# --- FONCTION DE FILTRAGE DES MISSIONS ---
def filter_missions_for_user(missions: list, user: User) -> list:
    authorized_sm_ids = [sm.id for sm in user.missions_autorisees] if hasattr(user, 'missions_autorisees') and user.missions_autorisees else []
    
    filtered_missions = []
    for m in missions:
        if m.resp_only:
            if user.role != Role.resp:
                continue
            
        if authorized_sm_ids:
            m.sous_missions = [sm for sm in m.sous_missions if sm.id in authorized_sm_ids]
            if not m.sous_missions:
                continue
        
        filtered_missions.append(m)
    return filtered_missions

# --- LISTE DES DÉCLARATIONS ---
@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def list_declarations(
    request: Request,
    site: Optional[str] = Query(None),
    mois: Optional[str] = Query(None),
    annee: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # On précise à SQLAlchemy d'utiliser la relation 'user' (liée à user_id)
    query = (
    select(Declaration)
    .join(User, Declaration.user_id == User.id) 
    .options(selectinload(Declaration.user))
)
    # --- 1. FILTRES DE SÉCURITÉ / RÔLES (Périmètre de visibilité) ---
    if current_user.role == Role.admin:
        # L'admin voit tout par défaut, on ne restreint rien ici
        pass
            
    elif current_user.role == Role.coordo:
        # Le coordo ne voit que son site
        query = query.where(User.site == current_user.site)
             
    elif current_user.role == Role.resp:
        # Le responsable voit ses décla + celles des TCP de sa matière/site
        query = query.where(
            or_(
                Declaration.user_id == current_user.id,
                and_(
                    User.role == Role.tcp,
                    User.site == current_user.site,
                    User.matiere == current_user.matiere
                )
            )
        )
    else:
        # Intervenant classique : seulement les siennes
        query = query.where(Declaration.user_id == current_user.id)

    # --- 2. FILTRES DYNAMIQUES (Appliqués à tous les rôles autorisés) ---
    
    # Filtre par Collaborateur spécifique (passé par l'URL ou bandeau)
    if user_id:
        query = query.where(Declaration.user_id == user_id)
    
    # Filtre par Site (pour Admin principalement, ou affinage Coordo)
    if site and site.strip():
        query = query.where(User.site == site)

    # Filtre par Mois
    if mois and mois.isdigit():
        query = query.where(Declaration.mois == int(mois))
        
    # Filtre par Année
    if annee and annee.isdigit():
        query = query.where(Declaration.annee == int(annee))
        
    # Filtre par Statut
    if statut and statut.strip():
        query = query.where(Declaration.statut == statut)

    # --- 3. EXÉCUTION ---
    query = query.order_by(Declaration.annee.desc(), Declaration.mois.desc(), Declaration.id.desc())
    result = await db.execute(query)
    declarations = result.scalars().all()

    # Récupération de l'user sélectionné pour le bandeau d'info
    selected_user = None
    if user_id:
        user_res = await db.execute(select(User).where(User.id == user_id))
        selected_user = user_res.scalar_one_or_none()

    return templates.TemplateResponse(
        "declarations/list.html",
        {
            "request": request, 
            "user": current_user, 
            "declarations": declarations,
            "mois_labels": MOIS_LABELS, 
            "sites": list(Site), 
            "statuts": list(StatutDeclaration),
            "selected_user": selected_user,
            # Indispensable pour garder les filtres sélectionnés dans le HTML
            "current_site": site,
            "current_mois": mois,
            "current_annee": annee,
            "current_statut": statut,
            "current_user_id": user_id,
        },
    )

# --- FORMULAIRE NOUVELLE DÉCLARATION ---
@router.get("/new", response_class=HTMLResponse)
async def new_declaration_form(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role in (Role.admin, Role.coordo):
        return RedirectResponse("/declarations?error=saisie_interdite_management", status_code=302)

    if not current_user.profil_complete:
        return RedirectResponse("/profile?warning=profil_incomplet", status_code=302)

    res_user = await db.execute(
        select(User).where(User.id == current_user.id).options(selectinload(User.missions_autorisees))
    )
    user_full = res_user.scalar_one()

    now = datetime.now()
    existing_res = await db.execute(
        select(Declaration.mois).where(
            Declaration.user_id == current_user.id, 
            Declaration.annee == now.year
        )
    )
    mois_deja_faits = existing_res.scalars().all()

    missions_result = await db.execute(
        select(Mission).where(Mission.is_active == True).options(selectinload(Mission.sous_missions)).order_by(Mission.ordre)
    )
    missions = filter_missions_for_user(missions_result.scalars().all(), user_full)

    return templates.TemplateResponse(
        "declarations/form.html",
        {
            "request": request, "user": user_full, "declaration": None,
            "missions": missions, "default_mois": now.month, "default_annee": now.year,
            "mois_labels": MOIS_LABELS, "lignes_map": {}, "mois_interdits": mois_deja_faits
        },
    )

# --- SAUVEGARDE NOUVELLE DÉCLARATION ---
@router.post("/new/")
@router.post("/new")
async def create_declaration(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. VERIFICATION DE SECURITE (Profil complet pour RESP et TCP)
    if current_user.role in [Role.resp, Role.tcp]:
        # On vérifie physiquement la présence des données de paiement
        champs_critiques = [
            current_user.nom, 
            current_user.prenom, 
            current_user.adresse, 
            current_user.nss_encrypted, 
            current_user.iban_encrypted
        ]
        
        if not all(val and str(val).strip() for val in champs_critiques):
            # On force la mise à jour du flag en base s'il était faux
            current_user.profil_complete = False
            await db.commit()
            return RedirectResponse("/profile?error=paiement_requis", status_code=303)

    # 2. RECUPERATION DES DONNEES DU FORMULAIRE
    form_data = await request.form()
    try:
        mois = int(form_data.get("mois", datetime.now().month))
        annee = int(form_data.get("annee", datetime.now().year))
    except ValueError:
        return RedirectResponse("/declarations?error=date_invalide", status_code=303)
        
    action = form_data.get("action", "brouillon")

    # 3. VERIFICATION DES DOUBLONS (Une seule déclaration par mois/annee par utilisateur)
    stmt_check = select(Declaration).where(
        Declaration.user_id == current_user.id,
        Declaration.mois == mois,
        Declaration.annee == annee
    )
    existing_check = await db.execute(stmt_check)
    if existing_check.scalars().first():
        return RedirectResponse(f"/declarations?error=deja_existant&m={mois}&a={annee}", status_code=303)

    # 4. CREATION DE LA DECLARATION PARENTE
    new_dec = Declaration(
        user_id=current_user.id,
        mois=mois,
        annee=annee,
        statut=StatutDeclaration.brouillon,
        site=current_user.site,
        programme=current_user.programme
    )
    db.add(new_dec)
    await db.flush()  # Pour récupérer l'ID de la déclaration

    # 5. AJOUT DES LIGNES (Missions) - VERSION SÉCURISÉE
    lignes_ajoutees = 0
    for key, value in form_data.items():
        if key.startswith("quantite_") and value:
            try:
                sm_id = int(key.split("_")[1])
                
                # RÉCUPÉRATION DE LA SOUS-MISSION POUR VÉRIFIER LE TYPE
                res_sm = await db.execute(
                    select(SousMission)
                    .options(selectinload(SousMission.mission))
                    .where(SousMission.id == sm_id)
                )
                sm = res_sm.scalar_one_or_none()
                
                if not sm: continue

                # --- LE VERROU SÉCURITÉ ---
                if sm.mission.resp_only:
                    quantite = 1.0  # On force à 1 peu importe la saisie
                else:
                    val_clean = str(value).replace(',', '.').strip()
                    quantite = float(val_clean)
                
                if quantite > 0:
                    nouvelle_ligne = LigneDeclaration(
                        declaration_id=new_dec.id, 
                        sous_mission_id=sm_id, 
                        quantite=quantite
                    )
                    db.add(nouvelle_ligne)
                    lignes_ajoutees += 1
            except (ValueError, IndexError):
                continue

            # 6. GESTION DE L'ACTION
            msg = "declaration_created" 

            if action == "soumettre":
                from datetime import date
                aujourdhui = date.today()
                date_ouverture = date(annee, mois, 1)

                if aujourdhui < date_ouverture:
                    # On force le mode brouillon car il est trop tôt
                    action = "brouillon"
                    msg = "saved_as_draft_early"
                    # Note : new_dec.statut est déjà StatutDeclaration.brouillon par défaut
                else:
                    # OK : On passe en soumise
                    new_dec.statut = StatutDeclaration.soumise
                    new_dec.soumise_le = datetime.now()
                    msg = "submitted"

            # 7. FINALISATION
            await db.commit()
            await db.refresh(new_dec)

            # On construit l'URL proprement
            target_url = f"/declarations/{new_dec.id}?msg={msg}"
            print(f"DEBUG: Redirection vers {target_url}")

            return RedirectResponse(url=target_url, status_code=303)

# --- DÉTAIL D'UNE DÉCLARATION ---
@router.get("/{decl_id}", response_class=HTMLResponse)
async def view_declaration(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Declaration)
        .options(
            selectinload(Declaration.user),
            selectinload(Declaration.lignes).selectinload(LigneDeclaration.sous_mission).selectinload(SousMission.mission),
        )
        .where(Declaration.id == decl_id)
    )
    declaration = result.scalar_one_or_none()
    if not declaration: return RedirectResponse("/declarations", status_code=302)

    allowed = False
    if current_user.role == Role.admin: allowed = True
    elif current_user.role == Role.coordo: allowed = (declaration.user.site == current_user.site)
    elif current_user.role == Role.resp:
        allowed = (declaration.user_id == current_user.id or (
            declaration.user.role == Role.tcp and 
            declaration.user.site == current_user.site and 
            declaration.user.matiere == current_user.matiere
        ))
    else: allowed = (declaration.user_id == current_user.id)

    if not allowed: return RedirectResponse("/declarations?error=acces_refuse", status_code=302)

    total = sum(l.quantite * l.sous_mission.tarif for l in declaration.lignes)
    return templates.TemplateResponse(
        "declarations/detail.html",
        {"request": request, "user": current_user, "declaration": declaration, "mois_labels": MOIS_LABELS, "total": total},
    )

# --- ACTIONS DE VALIDATION / REJET ---
@router.post("/{decl_id}/valider")
async def valider_declaration(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Vérification du rôle global
    if current_user.role not in (Role.admin, Role.coordo):
        return RedirectResponse("/declarations?error=non_autorise", status_code=303)

    # 2. Récupération de la déclaration avec son utilisateur
    result = await db.execute(
        select(Declaration)
        .options(selectinload(Declaration.user))
        .where(Declaration.id == decl_id)
    )
    declaration = result.scalar_one_or_none()

    # 3. Vérification de l'existence et du statut
    if not declaration:
        return RedirectResponse("/declarations?error=introuvable", status_code=303)

    if declaration.statut != StatutDeclaration.soumise:
        # Si déjà validée ou encore en brouillon, on redirige simplement vers le détail
        return RedirectResponse(f"/declarations/{decl_id}", status_code=303)

    # 4. Vérification du périmètre pour les coordinateurs
    if current_user.role == Role.coordo and declaration.user.site != current_user.site:
         return RedirectResponse("/declarations?error=hors_perimetre", status_code=303)

    # 5. Validation et enregistrement
    declaration.statut = StatutDeclaration.validee
    await db.commit()

    # 6. Redirection avec le paramètre de succès pour main.js
    return RedirectResponse(url=f"/declarations/{decl_id}?msg=validee", status_code=303)

@router.post("/{decl_id}/rejeter")
async def rejeter_declaration(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role not in (Role.admin, Role.coordo):
        return RedirectResponse("/declarations?error=non_autorise", status_code=302)

    form_data = await request.form()
    commentaire = form_data.get("commentaire_admin", "").strip()

    result = await db.execute(select(Declaration).options(selectinload(Declaration.user)).where(Declaration.id == decl_id))
    declaration = result.scalar_one_or_none()

    if declaration and declaration.statut == StatutDeclaration.soumise:
        if current_user.role == Role.coordo and declaration.user.site != current_user.site:
             return RedirectResponse("/declarations?error=hors_perimetre", status_code=302)
        
        declaration.statut = StatutDeclaration.brouillon
        declaration.commentaire_admin = commentaire 
        await db.commit()
    
    return RedirectResponse(request.headers.get("referer", "/declarations"), status_code=302)

# --- RÉOUVERTURE / RENVOI EN BROUILLON (ADMIN + COORDO) ---
@router.post("/{decl_id}/reouvrir")
async def reouvrir_declaration(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.admin, Role.coordo):
        return RedirectResponse(f"/declarations/{decl_id}?error=non_autorise", status_code=302)

    # 1. Récupération et vérification du motif
    form_data = await request.form()
    commentaire = form_data.get("commentaire_admin", "").strip()

    # Blocage serveur si le commentaire est vide
    if not commentaire:
        return RedirectResponse(f"/declarations/{decl_id}?error=motif_obligatoire", status_code=302)

    result = await db.execute(
        select(Declaration).options(selectinload(Declaration.user)).where(Declaration.id == decl_id)
    )
    declaration = result.scalar_one_or_none()

    if declaration and declaration.statut in (StatutDeclaration.validee, StatutDeclaration.soumise):
        if current_user.role == Role.coordo and declaration.user.site != current_user.site:
             return RedirectResponse(f"/declarations/{decl_id}?error=hors_perimetre", status_code=302)
        
        # 2. Application du changement
        declaration.statut = StatutDeclaration.brouillon
        declaration.commentaire_admin = commentaire
        
        await db.commit()
        return RedirectResponse(f"/declarations/{decl_id}?info=reouverte", status_code=302)
    
    return RedirectResponse(f"/declarations/{decl_id}", status_code=302)

# --- SUPPRESSION (ADMIN + COORDO) ---
@router.post("/{decl_id}/delete")
async def delete_declaration(
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in (Role.admin, Role.coordo):
        return RedirectResponse(f"/declarations/{decl_id}?error=non_autorise", status_code=302)

    result = await db.execute(select(Declaration).options(selectinload(Declaration.user)).where(Declaration.id == decl_id))
    declaration = result.scalar_one_or_none()

    if declaration:
        if current_user.role == Role.coordo and declaration.user.site != current_user.site:
            return RedirectResponse(f"/declarations/{decl_id}?error=hors_perimetre", status_code=302)

        await db.execute(delete(LigneDeclaration).where(LigneDeclaration.declaration_id == decl_id))
        await db.delete(declaration)
        await db.commit()
        return RedirectResponse("/declarations?info=supprime", status_code=302)
    
    return RedirectResponse("/declarations", status_code=302)

# --- FORMULAIRE ÉDITION (BROUILLON) ---
@router.get("/{decl_id}/edit", response_class=HTMLResponse)
async def edit_declaration_form(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Declaration)
        .options(selectinload(Declaration.lignes).selectinload(LigneDeclaration.sous_mission))
        .where(Declaration.id == decl_id)
    )
    declaration = result.scalar_one_or_none()
    if not declaration: return RedirectResponse("/declarations", status_code=302)

    # Vérification : Proprio en brouillon OU Admin/Coordo du site
    can_edit = (declaration.user_id == current_user.id and declaration.statut == StatutDeclaration.brouillon) or (current_user.role == Role.admin)
    if not can_edit: return RedirectResponse(f"/declarations/{decl_id}", status_code=302)

    res_user = await db.execute(
        select(User).where(User.id == declaration.user_id).options(selectinload(User.missions_autorisees))
    )
    user_full = res_user.scalar_one()

    missions_result = await db.execute(
        select(Mission).where(Mission.is_active == True).options(selectinload(Mission.sous_missions)).order_by(Mission.ordre)
    )
    missions = filter_missions_for_user(missions_result.scalars().all(), user_full)

    lignes_map = {l.sous_mission_id: l.quantite for l in declaration.lignes}
    return templates.TemplateResponse(
        "declarations/form.html",
        {
            "request": request, "user": current_user, "declaration": declaration, "missions": missions,
            "default_mois": declaration.mois, "default_annee": declaration.annee,
            "mois_labels": MOIS_LABELS, "lignes_map": lignes_map,
        },
    )

# --- MISE À JOUR ÉDITION (POST) ---
@router.post("/{decl_id}/edit/")
@router.post("/{decl_id}/edit")
async def update_declaration(
    request: Request,
    decl_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Declaration).where(Declaration.id == decl_id))
    declaration = result.scalar_one_or_none()
    if not declaration: return RedirectResponse("/declarations", status_code=302)

    form_data = await request.form()
    action = form_data.get("action", "brouillon")
    msg = "updated" # 🏷️ Message par défaut

    # --- 1. SÉCURITÉ ET GESTION DU STATUT ---
    if action == "soumettre":
        from datetime import date
        aujourdhui = date.today()
        date_ouverture = date(declaration.annee, declaration.mois, 1)

        if aujourdhui < date_ouverture:
            # 🔄 Au lieu de bloquer, on transforme la soumission en brouillon
            action = "brouillon"
            msg = "saved_as_draft_early"
        else:
            # ✅ La date est valide, on change le statut
            declaration.statut = StatutDeclaration.soumise
            declaration.soumise_le = datetime.now()
            declaration.commentaire_admin = None
            msg = "submitted"

    # --- 2. MISE À JOUR DES LIGNES (S'exécute même si action est devenue "brouillon") ---
    await db.execute(delete(LigneDeclaration).where(LigneDeclaration.declaration_id == decl_id))
    
    lignes_ajoutees = 0
    for key, value in form_data.items():
        if key.startswith("quantite_") and value:
            try:
                sm_id = int(key.split("_")[1])
                quantite = float(value.replace(',', '.'))
                if quantite > 0:
                    db.add(LigneDeclaration(declaration_id=decl_id, sous_mission_id=sm_id, quantite=quantite))
                    lignes_ajoutees += 1
            except (ValueError, IndexError): pass

    # --- 3. GESTION DU CAS VIDE ---
    if lignes_ajoutees == 0:
        await db.rollback()
        return RedirectResponse(f"/declarations/{decl_id}/edit?error=vide", status_code=303)

    await db.commit()
    # On ajoute le paramètre msg à l'URL pour ton front-end
    return RedirectResponse(f"/declarations/{decl_id}?msg={msg}", status_code=302)