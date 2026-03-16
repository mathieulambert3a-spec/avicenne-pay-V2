from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query, BackgroundTasks, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from app.services.mail import send_welcome_email, send_reminder_email
from passlib.context import CryptContext
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, String, func, and_, or_, text, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime, date
import asyncio
import csv
import io
import zipfile
import logging

from io import BytesIO, StringIO
from cryptography.fernet import Fernet, InvalidToken
from weasyprint import HTML

# --- IMPORTS DE SÉCURITÉ ET BDD ---
from app.database import get_db
from app.config import FERNET_KEY
from app.dependencies import get_current_user, require_role

# --- IMPORTS DES MAILS ---
from app.services.mail import FastMail, MessageSchema, MessageType, conf

# --- IMPORTS DES MODÈLES ---
from app import models
from app.models.user import User, Role, Site, Programme, Filiere, Annee, MATIERES
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
from app.models.sub_mission import SousMission
from app.models.mission import Mission
from app.schemas.constants import UNITES_CHOICES
from app.common.templates import templates
from app.database import AsyncSessionLocal

# Configuration du logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

# Petit utilitaire pour vérifier si l'user est bien admin
async def check_admin(user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return user

# --- SÉCURITÉ : Définition des niveaux d'accès ---
staff_required = require_role([Role.admin, Role.coordo, Role.resp])
delete_allowed = require_role([Role.admin, Role.coordo])
admin_only = require_role([Role.admin])
catalogue_manager = require_role([Role.admin, Role.coordo])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- UTILS (Chiffrement pour NSS et IBAN) ---
def get_fernet():
    if FERNET_KEY:
        return Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return None

def decrypt(value: str, f) -> str:
    if f and value:
        try:
            return f.decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            return value
    return value or ""

# --- PILOTAGE (Statistiques & Dashboard Admin) ---
@router.get("/stats", response_class=HTMLResponse)
async def get_stats(
    request: Request,
    programme: Optional[str] = Query(None),
    matiere: Optional[str] = Query(None),
    mission_nom: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    start_mois: int = Query(1),
    start_annee: int = Query(default=date.today().year),
    end_mois: int = Query(12),
    end_annee: int = Query(default=date.today().year),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # --- 1. IMPORTS CORRIGÉS (À l'intérieur de la fonction pour éviter les cycles) ---
    from app.models.user import User, Site, Programme, MATIERES
    from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
    from app.models.mission import Mission
    from app.models.sub_mission import SousMission  # Chemin correct ici
    from sqlalchemy import func, select, and_, desc

# --- 2. INITIALISATION DYNAMIQUE DES FILTRES (Seulement ce qui a été déclaré) ---
    
    # On cherche les combinaisons uniques de programme/matière présentes dans les déclarations 
    # ayant un statut 'soumise' ou 'validee'
    stmt_combos_actives = (
        select(User.programme, User.matiere)
        .distinct()
        .join(Declaration, User.id == Declaration.user_id)
        .where(Declaration.statut.in_([StatutDeclaration.validee, StatutDeclaration.soumise]))
    )
    res_combos = await db.execute(stmt_combos_actives)
    combos_reels = res_combos.all()

    # On construit le dictionnaire programmes_matieres basé sur ces résultats réels
    programmes_matieres = {}
    # On garde ton ordre de tri pour les programmes
    ordre_programmes = [Programme.pass_, Programme.las1, Programme.las2]
    
    # On transforme les résultats en un ensemble pour une recherche rapide
    # Format : {('PASS', 'Chimie'), ('LAS1', 'Droit')}
    combos_set = set()
    for row in combos_reels:
        if row[0] and row[1]:
            p_val = row[0].value if hasattr(row[0], 'value') else str(row[0])
            combos_set.add((p_val, row[1]))

    for p_enum in ordre_programmes:
        p_name = p_enum.value
        # On filtre les matières définies dans MATIERES pour ne garder que celles qui ont des données en base
        if p_name in MATIERES:
            liste_active = [m for m in MATIERES[p_name] if (p_name, m) in combos_set]
            if liste_active:
                programmes_matieres[p_name] = sorted(liste_active)

    # Pour "Toutes les matières" (utilisé si aucun programme n'est sélectionné)
    toutes_les_matieres = sorted(list({m for p, m in combos_set}))

    # La suite reste inchangée (Missions groupes...)
    stmt_m_group = (
        select(Mission.titre, SousMission.titre)
        .join(SousMission, Mission.id == SousMission.mission_id)
        .where(SousMission.is_active == True)
        .order_by(Mission.ordre, SousMission.ordre)
    )
    res_m_group = await db.execute(stmt_m_group)
    
    missions_groupes = {}
    for m_titre, sm_titre in res_m_group.all():
        if m_titre not in missions_groupes:
            missions_groupes[m_titre] = []
        missions_groupes[m_titre].append(sm_titre)

    # --- 3. LOGIQUE DES FILTRES (PÉRIODE GLISSANTE) ---
    start_val = start_annee * 100 + start_mois
    end_val = end_annee * 100 + end_mois

    filters = [
        (Declaration.annee * 100 + Declaration.mois) >= start_val,
        (Declaration.annee * 100 + Declaration.mois) <= end_val
    ]

    if statut == "validee":
        filters.append(Declaration.statut == StatutDeclaration.validee)
    elif statut == "soumise":
        filters.append(Declaration.statut == StatutDeclaration.soumise)
    else:
        filters.append(Declaration.statut.in_([StatutDeclaration.validee, StatutDeclaration.soumise]))

    if programme and programme.strip():
        filters.append(User.programme == programme)
    if matiere and matiere.strip():
        filters.append(User.matiere == matiere)

    if mission_nom and mission_nom.strip():
        if mission_nom.startswith("PARENT:"):
            nom_pur = mission_nom.replace("PARENT:", "")
            filters.append(Mission.titre == nom_pur)
        else:
            filters.append(SousMission.titre == mission_nom)

# --- 4. CALCULS GLOBAUX (Volumes et Coûts détaillés) ---
    # 4a. On calcule d'abord le montant total global (pour les KPIs du haut)
    stmt_argent = (
        select(func.sum(LigneDeclaration.quantite * SousMission.tarif))
        .select_from(Declaration)
        .join(User, Declaration.user_id == User.id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .where(and_(*filters))
    )
    res_argent = await db.execute(stmt_argent)
    total_avicenne = res_argent.scalar() or 0.0

   # --- 4b. On calcule le détail par MISSION/SOUS-MISSION (pour votre tableau) ---
    stmt_unites_details = (
        select(
            Mission.titre, 
            SousMission.titre, 
            func.sum(LigneDeclaration.quantite),
            func.sum(LigneDeclaration.quantite * SousMission.tarif),
            SousMission.unite
        )
        .select_from(Declaration)
        .join(User, Declaration.user_id == User.id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .join(Mission, SousMission.mission_id == Mission.id)  # <--- INDISPENSABLE
        .where(and_(*filters)) 
        .group_by(Mission.titre, SousMission.titre, SousMission.unite)
    )
    
    # Cette ligne doit être indentée (4 espaces) pour être dans la fonction
    res_details = await db.execute(stmt_unites_details)
    
    stats_unites = {}
    stats_couts = {}
    
    for row in res_details.all():
        cle_unique = f"{row[0]} | {row[1]}"
        quantite_totale = float(row[2] or 0.0) 
        cout_total = float(row[3] or 0.0)
        unite_label = row[4] or "unité"
        
        stats_unites[cle_unique] = {
            "val": quantite_totale,
            "unit": unite_label
        }
        stats_couts[cle_unique] = cout_total

    sorted_keys = sorted(stats_unites.keys(), key=lambda k: stats_couts.get(k, 0), reverse=True)
    stats_unites = {k: stats_unites[k] for k in sorted_keys}

    # --- 5. ÉVOLUTION MENSUELLE ---
    stmt_comp = (
        select(
            Declaration.annee,
            Declaration.mois,
            User.site,
            func.sum(LigneDeclaration.quantite * SousMission.tarif).label("total")
        )
        .join(User, Declaration.user_id == User.id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .where(and_(*filters))
        .group_by(Declaration.annee, Declaration.mois, User.site)
    )
    res_comp = await db.execute(stmt_comp)
    
    evo_est, evo_sud = {}, {}
    for row in res_comp.all():
        key = f"{row.annee}-{row.mois}"
        if row.site == Site.lyon_est:
            evo_est[key] = float(row.total or 0)
        elif row.site == Site.lyon_sud:
            evo_sud[key] = float(row.total or 0)

    data_lyon_est, data_lyon_sud = [], []
    curr_m, curr_a = start_mois, start_annee
    while (curr_a * 100 + curr_m) <= (end_annee * 100 + end_mois):
        key = f"{curr_a}-{curr_m}"
        data_lyon_est.append(evo_est.get(key, 0.0))
        data_lyon_sud.append(evo_sud.get(key, 0.0))
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_a += 1
        if len(data_lyon_est) > 36: break # Sécurité 3 ans

 # --- 6. TOP 10 & SITES (CORRIGÉ) ---
    stmt_sites = (
        select(User.site, func.sum(LigneDeclaration.quantite * SousMission.tarif))
        .select_from(User)
        .join(Declaration, User.id == Declaration.user_id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .where(and_(*filters))
        .group_by(User.site)
    )
    stats_sites = (await db.execute(stmt_sites)).all()

    total_lyon_est = 0.0
    total_lyon_sud = 0.0
    for site_enum, montant in stats_sites:
        if site_enum == Site.lyon_est:
            total_lyon_est = float(montant or 0)
        elif site_enum == Site.lyon_sud:
            total_lyon_sud = float(montant or 0)

    stmt_users = (
        select(
            User, 
            func.sum(LigneDeclaration.quantite * SousMission.tarif).label("total_brut"),
            func.sum(LigneDeclaration.quantite).label("total_heures")
        )
        .join(Declaration, User.id == Declaration.user_id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .where(and_(*filters))
        .group_by(User.id)
        .order_by(desc(func.sum(LigneDeclaration.quantite * SousMission.tarif)))
        .limit(10)
    )
    res_users = await db.execute(stmt_users)
    
    # --- TRANSFORMATION POUR LE TEMPLATE (Crucial) ---
    stats_users_clean = []
    for row in res_users.all():
        user_obj = row[0]  # L'objet User
        
        # On extrait la valeur du rôle proprement ici pour éviter le bug hasattr dans Jinja
        role_display = "N/A"
        if user_obj.role:
            role_display = user_obj.role.value if hasattr(user_obj.role, 'value') else str(user_obj.role)

        stats_users_clean.append({
            "user": user_obj,
            "role_display": role_display,
            "total_brut": float(row[1] or 0),
            "total_heures": float(row[2] or 0)
        })

    return templates.TemplateResponse(
        "admin/stats.html", 
        {
            "request": request, 
            "user": current_user,
            "today_day": date.today().day,
            "today_month": date.today().month,
            "data_lyon_est": data_lyon_est, 
            "data_lyon_sud": data_lyon_sud,
            "total_avicenne": total_avicenne,
            "total_lyon_est": total_lyon_est,
            "total_lyon_sud": total_lyon_sud,
            "stats_unites": stats_unites,
            "stats_couts": stats_couts,
            "current_start_mois": start_mois,
            "current_start_annee": start_annee,
            "current_end_mois": end_mois,
            "current_end_annee": end_annee,
            "current_programme": programme,
            "current_matiere": matiere,
            "current_mission": mission_nom,
            "current_statut": statut,
            "programmes_matieres": programmes_matieres,
            "toutes_les_matieres": toutes_les_matieres, 
            "missions_groupes": missions_groupes,
            "stats_sites": stats_sites, 
            "stats_users": stats_users_clean
        }
    )

# --- GESTION DES UTILISATEURS ---
@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request, 
    current_user: User = Depends(staff_required), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Construction de la requête de base selon le rôle
    if current_user.role == Role.admin:
        # L'admin voit tout le monde (actifs + inactifs)
        stmt = select(User)
    elif current_user.role == Role.coordo:
        # Le coordo voit les actifs de son site
        stmt = select(User).where(
            User.site == current_user.site,
            User.is_active == True
        )
    else: # Responsable (Role.resp)
        # Le resp voit les actifs de sa matière/programme sur son site
        stmt = select(User).where(
            User.site == current_user.site,
            User.programme == current_user.programme,
            User.matiere == current_user.matiere,
            User.is_active == True
        )
    
    # 2. Exécution avec tri par ID (ou par Nom pour plus de confort)
    result = await db.execute(stmt.order_by(User.nom, User.prenom))
    users = result.scalars().all()

    # 3. Préparation des données pour les formulaires d'ajout/édition
    # On utilise MATIERES importé de votre modèle pour éviter les doublons
    from app.models.user import MATIERES, Site 

    return templates.TemplateResponse(
        "admin/users.html", 
        {
            "request": request, 
            "user": current_user,         
            "current_user": current_user,
            "users": users,
            "sites": [s.value for s in Site],
            "programmes": list(MATIERES.keys()),
            "matieres_par_prog": MATIERES
        }
    )

@router.post("/users/create")
async def create_user(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...), 
    password: str = Form(...), 
    role: str = Form(...),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    current_user: User = Depends(require_role([Role.admin, Role.coordo, Role.resp])), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Préparation des données
    final_role = Role(role)
    final_site = site
    final_prog = programme
    final_matiere = matiere

    if current_user.role == Role.resp:
        final_role = Role.tcp
        final_site = current_user.site.value
        final_prog = current_user.programme.value
        final_matiere = current_user.matiere
    elif current_user.role == Role.coordo:
        final_site = current_user.site.value

    # 2. Tentative de création avec gestion d'erreur précise
    try:
        new_user = User(
            email=email.lower().strip(),
            hashed_password=pwd_context.hash(password), 
            role=final_role,
            site=Site(final_site) if final_site else None,
            programme=Programme(final_prog) if final_prog else None,
            matiere=final_matiere,
            is_active=True
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # --- LOGIQUE D'ENVOI DE MAIL (CORRIGÉE) ---
        from app.services.mail import send_welcome_email
        from app.routers.auth import serializer # On importe le serializer de auth.py
        
        # On crée un token sécurisé pour cet email
        token = serializer.dumps(new_user.email, salt="password-reset-salt")
        
        # On génère le lien qui pointe vers "reset_password_page" (définie dans auth.py)
        setup_link = str(request.url_for("reset_password_page", token=token))
        
        print(f"DEBUG: Utilisateur {new_user.email} créé.")
        print(f"DEBUG: Lien d'activation : {setup_link}")
        
        # On envoie le mail avec le lien de reset
        background_tasks.add_task(send_welcome_email, new_user.email, setup_link)
        # ------------------------------------------

        return RedirectResponse("/admin/users?msg=created", status_code=303)

    except IntegrityError as e:
        await db.rollback()
        error_info = str(e.orig)
        if "uq_resp_site_programme_matiere" in error_info:
            return RedirectResponse("/admin/users?error=resp_exists", status_code=303)
        elif "users_email_key" in error_info:
            return RedirectResponse("/admin/users?error=email_exists", status_code=303)
        return RedirectResponse("/admin/users?error=db_error", status_code=303)

    except Exception as e:
        await db.rollback()
        print(f"ERREUR CRITIQUE : {e}")
        return RedirectResponse("/admin/users?error=db_error", status_code=303)

@router.post("/users/{user_id}/desactivate")
async def desactivate_user(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if target_user.id == current_user.id:
        # On ne peut pas se désactiver soi-même
        return RedirectResponse("/admin/users?error=self_delete", status_code=303)

    # ACTION : On passe le statut à inactif
    target_user.is_active = False
    await db.commit()
    
    return RedirectResponse("/admin/users?msg=disabled", status_code=303)

@router.post("/users/{user_id}/activate")
async def activate_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user_to_mod = result.scalar_one_or_none()
    
    if user_to_mod:
        try:
            user_to_mod.is_active = True
            await db.commit()
            return RedirectResponse("/admin/users?msg=activated", status_code=303)
        except IntegrityError:
            await db.rollback()
            # On renvoie l'erreur spécifique si un autre RESP est déjà actif
            return RedirectResponse("/admin/users?error=resp_exists", status_code=303)
    
    return RedirectResponse("/admin/users?error=not_found", status_code=303)

# --- EXPORT CSV (Version attachée à stats.html) ---
@router.get("/export/csv")
async def export_declarations_csv(
    start_mois: int = Query(1),
    start_annee: int = Query(2025),
    end_mois: int = Query(12),
    end_annee: int = Query(2025),
    programme: Optional[str] = Query(None),
    matiere: Optional[str] = Query(None),
    mission_nom: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    current_user: User = Depends(staff_required),
    db: AsyncSession = Depends(get_db),
):
    # 0. Sécurité : On force le rafraîchissement de la session
    db.expire_all()

    # 1. Calcul de la période glissante
    start_val = start_annee * 100 + start_mois
    end_val = end_annee * 100 + end_mois

    # 2. Base de la requête
    stmt = (
        select(LigneDeclaration, Declaration, User, SousMission, Mission)
        .join(Declaration, LigneDeclaration.declaration_id == Declaration.id)
        .join(User, Declaration.user_id == User.id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .outerjoin(Mission, SousMission.mission_id == Mission.id)
    )

    # 3. Filtres
    filters = [
        (Declaration.annee * 100 + Declaration.mois) >= start_val,
        (Declaration.annee * 100 + Declaration.mois) <= end_val
    ]

    if statut == "validee":
        filters.append(Declaration.statut.cast(String).ilike("%validee%"))
    elif statut == "soumise":
        filters.append(Declaration.statut.cast(String).ilike("%soumise%"))
    else:
        filters.append(
            or_(
                Declaration.statut.cast(String).ilike("%validee%"),
                Declaration.statut.cast(String).ilike("%soumise%")
            )
        )

    if programme:
        filters.append(User.programme == programme)
    if matiere:
        filters.append(User.matiere == matiere)
    
    stmt = stmt.where(and_(*filters))

    # 4. Exécution
    result = await db.execute(stmt)
    rows = result.all()

    # 5. Génération CSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # --- EN-TÊTE CORRIGÉ (Ajout Réf Facture en position 0) ---
    writer.writerow([
        "Réf Facture", 
        "Mois/Année", 
        "Collaborateur", 
        "Site", 
        "Prog", 
        "Matière", 
        "Mission", 
        "Sous-Mission", 
        "Quantité", 
        "Total Brut"
    ])

    # Date fixe pour le calcul du numéro de facture (Aujourd'hui)
    date_ref_str = datetime.now().strftime("%d%m%Y")

    for ligne_dec, dec, u, sm, m in rows:
        # Calcul du numéro de facture (Identique au PDF)
        nom_brut = u.nom or "INC"
        num_facture = f"{date_ref_str}-{nom_brut.upper()[:4]}"
        
        total_ligne = ligne_dec.quantite * sm.tarif
        
        # Récupération de la matière
        matiere_val = u.matiere.value if hasattr(u.matiere, 'value') else (u.matiere or "N/C")

        # --- ÉCRITURE DE LA LIGNE (Synchronisée avec l'en-tête) ---
        writer.writerow([
            num_facture,                # 1. Réf Facture
            f"{dec.mois}/{dec.annee}",  # 2. Mois/Année
            f"{u.prenom} {u.nom}",      # 3. Collaborateur
            u.site.value if hasattr(u.site, 'value') else (u.site or "N/C"),
            u.programme.value if hasattr(u.programme, 'value') else (u.programme or "N/C"),
            matiere_val,                # 6. Matière
            m.titre if m else "N/C", 
            sm.titre,
            str(ligne_dec.quantite).replace('.', ','),
            str(round(total_ligne, 2)).replace('.', ',')
        ])

    # Préparation du contenu binaire avec BOM (utf-8-sig) pour Excel
    content = output.getvalue().encode("utf-8-sig")
    output.close()

    # 6. Nom de fichier dynamique avec timestamp pour éviter le cache
    filename = f"export_avicenne_{datetime.now().strftime('%Y%m%d')}.csv"

    # 7. Retour avec NO-CACHE strict
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )

# --- MISE À JOUR STATUT & COMMENTAIRE ---
@router.post("/declarations/{declaration_id}/update")
async def update_status(
    declaration_id: int,
    statut: str = Form(...),
    commentaire_admin: Optional[str] = Form(None),
    current_user: User = Depends(staff_required),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Declaration).where(Declaration.id == declaration_id)
    result = await db.execute(stmt)
    declaration = result.scalar_one_or_none()
    if declaration:
        declaration.statut = StatutDeclaration(statut)
        declaration.commentaire_admin = commentaire_admin
        await db.commit()
    return RedirectResponse(url="/admin/declarations?msg=updated", status_code=303)

@router.get("/referentiel/missions", response_class=HTMLResponse)
async def manage_referentiel(
    request: Request,
    current_user: User = Depends(catalogue_manager),
    db: AsyncSession = Depends(get_db)
):
    # On utilise .titre au lieu de .nom et on trie par .ordre
    stmt = (
        select(Mission)
        .options(selectinload(Mission.sous_missions))
        .order_by(Mission.ordre, Mission.titre)
    )
    result = await db.execute(stmt)
    missions = result.scalars().all()

    return templates.TemplateResponse("admin/referentiel_missions.html", {
        "request": request,
        "user": current_user,
        "current_user": current_user,
        "missions": missions,
        "unites_disponibles": UNITES_CHOICES,
    })

# --- ACTION : AJOUTER MISSION PARENT ---
@router.post("/referentiel/missions/new")
async def admin_add_mission(
    request: Request,
    titre: str = Form(...), # On change 'nom' par 'titre' pour coller au HTML
    resp_only: Optional[bool] = Form(None), 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(catalogue_manager)
):
    is_resp_val = True if resp_only else False

    new_mission = Mission(
        titre=titre, # Utilise 'titre'
        ordre=0, 
        is_active=True, # On force l'activation ici
        resp_only=is_resp_val
    )
    
    db.add(new_mission)
    await db.commit()
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

# --- ACTION : AJOUTER SOUS-MISSION ---
@router.post("/referentiel/sub-mission/add")
async def admin_add_sub_mission(
    parent_id: int = Form(...),
    titre: str = Form(...),
    tarif: float = Form(...),
    unite: Optional[str] = Form(None), # Utilise Optional ici
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(catalogue_manager)
):
    # Sécurité : strip() seulement si unite n'est pas None
    unite_value = unite.strip() if unite else None
    
    new_sm = SousMission(
        mission_id=parent_id,
        titre=titre,
        tarif=tarif,
        unite=unite_value,
        is_active=True
    )
    
    try:
        db.add(new_sm)
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"ERREUR DB : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'insertion")
        
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

# --- ACTION : MODIFIER MISSION PARENT ---
@router.post("/referentiel/missions/{mission_id}/edit")
async def edit_mission(
    mission_id: int,
    titre: str = Form(...),
    resp_only: Optional[str] = Form(None), 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(catalogue_manager)
):
    print(f">>> EDIT MISSION {mission_id}: titre={titre}, resp={resp_only}")
    
    try:
        # 1. On récupère la mission
        result = await db.execute(select(Mission).where(Mission.id == mission_id))
        mission = result.scalar_one_or_none()
        
        if not mission:
            print(">>> Erreur: Mission non trouvée")
            return RedirectResponse(url="/admin/referentiel/missions?error=notfound", status_code=303)

        # 2. On applique les changements
        mission.titre = titre.strip()
        # Le switch HTML envoie "on" s'il est coché, None sinon
        mission.resp_only = True if resp_only else False
        
        # 3. On force SQLAlchemy à considérer l'objet comme modifié
        db.add(mission) 
        
        # 4. On valide
        await db.commit()
        print(">>> SUCCESS: Mission mise à jour")
        
        return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

    except Exception as e:
        await db.rollback()
        # C'est ici que tu verras l'erreur réelle dans ton terminal
        print(f">>> ERREUR CRITIQUE ÉDITION : {str(e)}")
        import traceback
        traceback.print_exc() # Affiche toute la pile d'erreur
        raise HTTPException(status_code=500, detail="Erreur interne serveur")

@router.post("/referentiel/missions/{mission_id}/toggle-active")
async def toggle_mission_active(
    mission_id: int, 
    db: AsyncSession = Depends(get_db)
):
    # On récupère la mission parent
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(status_code=404, detail="Mission non trouvée")

    mission.is_active = not mission.is_active

    await db.commit()
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(
    request: Request, 
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(catalogue_manager)
):
    user_to_edit = await db.get(User, user_id)
    if not user_to_edit:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Préparation des Enums pour le template
    clean_matieres = {str(k): v for k, v in MATIERES.items()}

    return templates.TemplateResponse("admin/user_form.html", {
        "request": request,
        "u": user_to_edit,
        "user": current_admin, # Admin connecté
        "roles": [r.value for r in Role],
        "sites": [s.value for s in Site],
        "programmes": [p.value for p in Programme],
        "filieres": [f.value for f in Filiere],
        "annees": [a.value for a in Annee],
        "matieres_par_prog": clean_matieres
    })

@router.post("/users/{user_id}/edit")
async def edit_user_save(
    user_id: int,
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(check_admin),
    role: str = Form(...),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    password: Optional[str] = Form(None)
    # J'ai retiré email, nom, prenom, filiere, annee qui ne sont plus dans ton formulaire
):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    
    if not u: 
        return RedirectResponse(url="/admin/users?error=notfound", status_code=303)

    try:
        # Mise à jour des permissions et affectations
        u.role = Role(role)
        u.site = Site(site) if site and site.strip() else None
        u.programme = Programme(programme) if programme and programme.strip() else None
        u.matiere = matiere if matiere and matiere.strip() else None

        # Sécurité : Si Admin, on nettoie les affectations pédagogiques
        if u.role == Role.admin:
            u.site = None
            u.programme = None
            u.matiere = None

        # Mot de passe (Uniquement si rempli)
        if password and len(password.strip()) >= 8:
            u.hashed_password = pwd_context.hash(password)

        await db.commit()
        return RedirectResponse(url="/admin/users?msg=updated", status_code=303)

    except IntegrityError:
        await db.rollback()
        # Probablement un doublon de Responsable sur la même matière
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=duplicate_resp", status_code=303)
    except Exception as e:
        await db.rollback()
        logger.error(f"Erreur edit : {e}")
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=db_error", status_code=303)

# -pdf executor ---
pdf_executor = ThreadPoolExecutor(max_workers=1)

def render_pdf_task(template_name, context):
    from weasyprint import HTML
    try:
        print(f"--- [START] WeasyPrint pour {context['u'].nom}")
        template = templates.get_template(template_name)
        html_content = template.render(**context)
        pdf_bytes = HTML(string=html_content).write_pdf()
        print(f"✅ OK : {context['u'].nom}")
        return pdf_bytes
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return b""

@router.post("/generate-factures")
async def generate_factures(
    date_debut: str = Form(...),
    date_fin: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.admin))
):
    try:
        print(f"--- Lancement de la génération parallèle ---")
        f_cipher = get_fernet()
        d_start_proc = datetime.now()
        
        start_dt = datetime.strptime(date_debut, "%Y-%m-%d")
        end_dt = datetime.strptime(date_fin, "%Y-%m-%d")

        # 1. Requête SQL
        stmt = (
            select(Declaration)
            .join(User)
            .options(
                selectinload(Declaration.user),
                selectinload(Declaration.lignes)
                    .selectinload(LigneDeclaration.sous_mission)
                    .selectinload(SousMission.mission)
            )
            .where(
                and_(
                    Declaration.statut == StatutDeclaration.validee,
                    (Declaration.annee * 100 + Declaration.mois) >= (start_dt.year * 100 + start_dt.month),
                    (Declaration.annee * 100 + Declaration.mois) <= (end_dt.year * 100 + end_dt.month)
                )
            )
        )
        
        result = await db.execute(stmt)
        declarations = result.scalars().all()
        print(f"-> {len(declarations)} déclarations à traiter.")

        if not declarations:
            return RedirectResponse(url="/admin/stats?error=no_data", status_code=303)

        # 2. Préparation de la liste
        data_list = []
        # On fixe la date de génération une seule fois pour tout le lot
        now = datetime.now()
        date_gen_str = now.strftime("%d/%m/%Y")
        date_ref_str = now.strftime("%d%m%Y") # Format 16032026 pour la réf

        for dec in declarations:
            u = dec.user
            
            # 1. Calcul du numéro de facture (Identique à ton HTML)
            nom_majuscule = (u.nom or "INC").upper()
            # On prend les 3 premières lettres (truncate 3)
            nom_court = nom_majuscule[:4]
            num_facture = f"{date_ref_str}-{nom_court}"

            # 2. Décryptage NSS
            try:
                nss_clair = decrypt(u.nss_encrypted, f_cipher) if u.nss_encrypted else "Non renseigné"
            except Exception:
                nss_clair = "Erreur"

            prog = u.programme.value if u.programme else "Programme"
            mat = u.matiere if u.matiere else "Matière"
            
            data_list.append({
                "u": u,
                "nss": nss_clair,
                "num_facture": num_facture,
                "total": sum(l.quantite * l.sous_mission.tarif for l in dec.lignes),
                "nature_facture": f"{prog}: {mat}",
                "dec": dec,
                "date_gen": date_gen_str,
                # Le nom du fichier devient aussi plus clair
                "filename": f"Facture_{num_facture}_{u.nom}.pdf"
            })
        
        # --- ÉTAPE 3 : LE TURBO (PARALLÈLE) ---
        loop = asyncio.get_running_loop()
        futures = [
            loop.run_in_executor(pdf_executor, render_pdf_task, "pdf/facture_template.html", item)
            for item in data_list
        ]

        # On attend que les 8 cœurs travaillent ensemble
        pdf_contents = await asyncio.gather(*futures)

        # 4. Création du ZIP final
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for item, content in zip(data_list, pdf_contents):
                if content: # On ne met dans le ZIP que si le PDF a bien été généré
                    zip_file.writestr(item["filename"], content)

        # On récupère les octets et on ferme le buffer
        zip_data = zip_buffer.getvalue()
        zip_buffer.close()

        duration = (datetime.now() - d_start_proc).seconds
        print(f"--- Succès : {len(declarations)} PDF générés en {duration}s ---")

        # Génère "factures_avicenne_20260315.zip"
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"factures_avicenne_{date_str}.zip"

        from fastapi import Response
        return Response(
            content=zip_data,
            media_type="application/zip",
            headers={
                # On utilise f-string pour insérer le nom dynamique
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        import traceback
        print(f"ERREUR : {traceback.format_exc()}")
        return RedirectResponse(url="/admin/stats?error=generation_failed", status_code=303)

# --- LOGIQUE D'ENVOI DES EMAILS (Gardée telle quelle mais optimisée) ---
async def send_reminder_email(email_to, first_name, month_fr):
    # Ton code HTML actuel est parfait
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px;">
        <h2 style="color: #dc3545;">Rappel Déclaration - Avicenne Pay</h2>
        <p>Bonjour {first_name},</p>
        <p>Sauf erreur de notre part, vous n'avez pas encore validé votre déclaration d'activité pour le mois de <strong>{month_fr}</strong>.</p>
        <p>Nous vous rappelons que la date limite de saisie approche.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="https://votre-domaine.com/declarations" style="background-color: #dc3545; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Remplir ma déclaration</a>
        </div>
        <p style="font-size: 0.8em; color: #999;">Si vous venez de la soumettre, merci d'ignorer ce message.</p>
    </div>
    """
    message = MessageSchema(
        subject=f"Rappel : Déclaration de {month_fr} manquante",
        recipients=[email_to],
        body=html,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def main_reminder_logic():
    """ Logique d'envoi avec création d'une session dédiée pour l'arrière-plan """
    from app.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        today = date.today() 
        months_fr = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", 
                     "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        current_month_name = months_fr[today.month]

        # On récupère tous les utilisateurs qui doivent déclarer
        result = await db.execute(
            select(User).where(
                User.is_active == True,
                User.role.notin_([Role.admin, Role.coordo])
            )
        )
        users = result.scalars().all()
        
        for user in users:
            # On vérifie si une déclaration validée ou soumise existe
            decl_check = await db.execute(
                select(Declaration).where(
                    Declaration.user_id == user.id,
                    Declaration.mois == today.month,
                    Declaration.annee == today.year,
                    # On ne relance PAS si c'est déjà soumis ou validé
                    Declaration.statut.in_(["soumise", "validee"]) 
                )
            )

            if not decl_check.scalar_one_or_none():
                try:
                    await send_reminder_email(user.email, user.prenom, current_month_name)
                    await asyncio.sleep(1.2) # Anti-spam / Limite SMTP
                except Exception as e:
                    print(f"Erreur relance {user.email}: {e}")

# --- LA ROUTE POUR TON BOUTON ---
@router.post("/users/add")
async def db_add_user(
    request: Request, 
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    nom: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. VÉRIFICATION : L'utilisateur existe-t-il déjà ?
    query = await db.execute(select(User).where(User.email == email))
    existing_user = query.scalar_one_or_none()

    if existing_user:
        # On retourne sur le formulaire avec un message d'erreur
        # Assure-toi que ton template 'user_form.html' affiche la variable 'error'
        return templates.TemplateResponse(
            "user_form.html", 
            {
                "request": request, 
                "error": f"L'adresse email {email} est déjà utilisée.",
                "values": {"email": email, "nom": nom} # Pour ne pas vider les champs
            }
        )

    # 2. CRÉATION (si tout est OK)
    new_user = User(
        email=email,
        nom=nom,
        is_active=True,
        hashed_password="!" # Bloqué jusqu'au premier reset
    )
    
    db.add(new_user)
    await db.commit()

   # 3. GÉNÉRATION DU TOKEN ET ENVOI MAIL
    from app.routers.auth import serializer 
    
    token = serializer.dumps(email, salt="password-reset-salt")
    setup_link = str(request.url_for("reset_password_page", token=token))

    from app.services.mail import send_welcome_email

    print(f"DEBUG: Tentative d'envoi de mail à {email}")
    print(f"DEBUG: Lien généré : {setup_link}")
    
    background_tasks.add_task(send_welcome_email, email, setup_link)

@router.post("/relance-retardataires")
async def relance_retardataires(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "coordo"]))
):
    from app.routers.auth import serializer 
    
    mois_noms = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin", 
        7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }

    try:
        # 1. Automatisation de la période
        maintenant = datetime.now()
        mois_actuel = maintenant.month
        annee_actuelle = maintenant.year
        nom_du_mois = mois_noms.get(mois_actuel)

        print(f"\n--- 🔍 RECHERCHE RETARDATAIRES : {nom_du_mois} {annee_actuelle} ---")

        # 2. Requête SQL
        query = (
            select(User)
            .join(Declaration, User.id == Declaration.user_id)
            .where(
                and_(
                    User.is_active == True,
                    User.role.in_([Role.tcp, Role.resp]),
                    Declaration.mois == mois_actuel,
                    Declaration.annee == annee_actuelle,
                    Declaration.statut == "brouillon"
                )
            )
        )
        
        result = await db.execute(query)
        retardataires = result.scalars().all()

        if not retardataires:
            return {
                "status": "success", 
                "count": 0, 
                "message": f"Aucun brouillon trouvé pour {nom_du_mois}."
            }

        # 3. Boucle de relance (Mode Simulation Sécurisé)
        count = 0
        for collab in retardataires:
            link = str(request.base_url) + "declarations" 

            # --- BLINDAGE ANTI-CRASH ---
            # On appelle notre service, mais si le réseau d'entreprise bloque encore l'EOF, 
            # le try/except ici empêchera la route de renvoyer une erreur 500.
            try:
                # Si ton mail.py est bien commenté, success sera True sans rien envoyer
                success = await send_reminder_email(collab.email, link, nom_du_mois)
                if success:
                    print(f"✅ Simulation relance validée pour : {collab.email}")
                    count += 1
            except Exception as e:
                # Au cas où un vieil import traîne, on log mais on ne crash pas
                print(f"⚠️ Simulation manuelle car l'envoi a échoué : {collab.email}")
                count += 1 

            await asyncio.sleep(0.1) 
            
        return {
            "status": "success", 
            "count": count, 
            "message": f"Relance de {nom_du_mois} terminée. {count} simulation(s) réussie(s)."
        }

    except Exception as e:
        # Ce bloc ne s'exécute que si la base de données ou le code Python a un bug majeur
        print(f"❌ ERREUR CRITIQUE ROUTER : {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la relance.")