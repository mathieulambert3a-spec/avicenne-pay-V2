from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from sqlalchemy import String, select, func, and_, or_, text, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import Optional, List
import csv
import io
import zipfile

from io import BytesIO, StringIO
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except OSError:
    WEASYPRINT_AVAILABLE = False
    print("⚠️ WeasyPrint non chargé (GTK manquant). Les exports PDF seront désactivés.")
#from weasyprint import HTML

from app.database import get_db
from app.config import FERNET_KEY
from app.dependencies import get_current_user, require_role

# Imports des modèles
from app.models.user import User, Role, Site, Programme, Filiere, Annee, MATIERES
from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
from app.models.sub_mission import SousMission
from app.models.mission import Mission
from app.schemas.constants import UNITES_CHOICES

import logging
# Configuration d'un logger pour voir ce qui bloque
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

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
    start_annee: int = Query(datetime.now().year),
    end_mois: int = Query(12),
    end_annee: int = Query(datetime.now().year),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # --- 1. IMPORTS CORRIGÉS (À l'intérieur de la fonction pour éviter les cycles) ---
    from app.models.user import User, Site, Programme, MATIERES
    from app.models.declaration import Declaration, LigneDeclaration, StatutDeclaration
    from app.models.mission import Mission
    from app.models.sub_mission import SousMission  # Chemin correct ici
    from sqlalchemy import func, select, and_, desc

    # --- 2. INITIALISATION DES LISTES POUR FILTRES ---
    stmt_mat_existantes = select(User.matiere).where(User.matiere != None).distinct()
    res_mat = await db.execute(stmt_mat_existantes)
    matieres_en_base = {row[0] for row in res_mat.all()}

    programmes_matieres = {}
    ordre_programmes = [Programme.pass_, Programme.las1, Programme.las2]

    for p_enum in ordre_programmes:
        p_name = p_enum.value
        if p_name in MATIERES:
            liste_triee = [m for m in MATIERES[p_name] if m in matieres_en_base]
            if liste_triee:
                programmes_matieres[p_name] = liste_triee

    toutes_les_matieres = []
    for p_name in MATIERES:
        for m in MATIERES[p_name]:
            if m in matieres_en_base and m not in toutes_les_matieres:
                toutes_les_matieres.append(m)

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

    # --- 4. CALCULS GLOBAUX ---
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

    stmt_unites = (
        select(SousMission.unite, func.sum(LigneDeclaration.quantite))
        .select_from(Declaration)
        .join(User, Declaration.user_id == User.id)
        .join(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .where(and_(*filters)) 
        .group_by(SousMission.unite)
    )
    res_unites = await db.execute(stmt_unites)
    stats_unites = {row[0]: row[1] for row in res_unites.all() if row[0]}

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

    # --- 6. TOP 10 & SITES ---
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

    return templates.TemplateResponse(
        "admin/stats.html", 
        {
            "request": request, 
            "user": current_user,
            "data_lyon_est": data_lyon_est, 
            "data_lyon_sud": data_lyon_sud,
            "total_avicenne": total_avicenne,
            "total_lyon_est": total_lyon_est,
            "total_lyon_sud": total_lyon_sud,
            "stats_unites": stats_unites,
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
            "stats_users": res_users.all()
        }
    )

# --- EXPORT STATS ---
@router.get("/stats/export-csv")
async def export_stats_csv(
    start_mois: int = Query(1),
    start_annee: int = Query(2025),
    end_mois: int = Query(12),
    end_annee: int = Query(2026),
    programme: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.admin))
):
    # 1. Calcul de la période
    start_val = start_annee * 100 + start_mois
    end_val = end_annee * 100 + end_mois

    # 2. Construction des filtres
    filters = [
        (Declaration.annee * 100 + Declaration.mois) >= start_val,
        (Declaration.annee * 100 + Declaration.mois) <= end_val
    ]

    # LOGIQUE DE STATUT ULTRA-FIABLE (Comparaison textuelle)
    if statut == "validee":
        filters.append(Declaration.statut == "validee")
    elif statut == "soumise":
        filters.append(Declaration.statut == "soumise")
    else:
        # "Soumise & Validée" : Tout sauf ce qui contient 'brouillon'
        # On utilise cast pour être certain que la base de données compare du texte
        filters.append(Declaration.statut.cast(String) != "brouillon")

    if programme and programme.strip():
        filters.append(Declaration.programme == programme)

    # 3. La Requête avec OUTERJOIN (Pour ne perdre aucune ligne validée)
    stmt = (
        select(
            User.nom, 
            User.prenom, 
            Declaration.site,
            Declaration.statut,
            Declaration.annee, 
            Declaration.mois,
            Declaration.programme,
            func.coalesce(Mission.titre, "Mission Inconnue").label("m_titre"), 
            func.coalesce(SousMission.titre, "Sous-mission Inconnue").label("sm_titre"),
            LigneDeclaration.quantite,
            SousMission.unite, 
            func.coalesce(SousMission.tarif, 0).label("tarif_unit"),
            (LigneDeclaration.quantite * func.coalesce(SousMission.tarif, 0)).label("total_ligne")
        )
        .select_from(Declaration)
        .outerjoin(User, Declaration.user_id == User.id)
        .outerjoin(LigneDeclaration, Declaration.id == LigneDeclaration.declaration_id)
        .outerjoin(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .outerjoin(Mission, SousMission.mission_id == Mission.id)
        .where(and_(*filters))
        .order_by(Declaration.annee.desc(), Declaration.mois.desc(), User.nom)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # 4. Génération du CSV
    output = StringIO()
    writer = csv.writer(output, delimiter=';')
    # En-tête (13 colonnes)
    writer.writerow(["Nom", "Prénom", "Site", "Statut", "Mois", "Année", "Prog", "Mission", "Sous-Mission", "Qté", "Unité", "Tarif", "Total"])

    for r in rows:
        # Conversion sécurisée des Enums (Statut, Site, Programme)
        s_text = r.statut.value if hasattr(r.statut, 'value') else str(r.statut)
        site_text = r.site.value if hasattr(r.site, 'value') else str(r.site)
        prog_text = r.programme.value if hasattr(r.programme, 'value') else str(r.programme)

        writer.writerow([
            r.nom or "N/A", 
            r.prenom or "N/A", 
            site_text, 
            s_text, 
            r.mois, 
            r.annee, 
            prog_text,
            r.m_titre, 
            r.sm_titre,
            str(r.quantite).replace('.', ','), 
            r.unite or "unité",
            str(r.tarif_unit).replace('.', ','), 
            str(round(r.total_ligne, 2)).replace('.', ',')
        ])

    # BOM UTF-8 pour Excel et retour du flux
    content = "\ufeff" + output.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=export_stats.csv"}
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
    email: str = Form(...), 
    password: str = Form(...), 
    role: str = Form(...),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    current_user: User = Depends(staff_required), 
    db: AsyncSession = Depends(get_db)
):
    # 1. Préparation des données selon les droits du créateur
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

    # 2. Tentative de création
    try:
        new_user = User(
            email=email.lower().strip(), # Sécurité : email en minuscules et sans espaces
            hashed_password=pwd_context.hash(password), 
            role=final_role,
            site=Site(final_site) if final_site else None,
            programme=Programme(final_prog) if final_prog else None,
            matiere=final_matiere,
            is_active=True # On s'assure qu'il est actif par défaut
        )
        db.add(new_user)
        await db.commit()
        return RedirectResponse("/admin/users?msg=created", status_code=303)

    except IntegrityError:
        # En cas de doublon d'email (UniqueViolationError)
        await db.rollback()
        return RedirectResponse("/admin/users?error=email_exists", status_code=303)
    
    except Exception as e:
        # Pour toute autre erreur imprévue
        await db.rollback()
        print(f"Erreur lors de la création : {e}")
        return RedirectResponse("/admin/users?error=db_error", status_code=303)

@router.post("/users/{user_id}/edit")
async def edit_user_save(
    user_id: int,
    email: str = Form(...),
    role: str = Form(...),
    site: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    current_user: User = Depends(staff_required),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u: raise HTTPException(status_code=404)

    u.email = email
    u.role = Role(role)
    u.site = Site(site) if site else None
    u.programme = Programme(programme) if programme else None
    u.matiere = matiere
    if password and len(password.strip()) >= 8:
        u.hashed_password = pwd_context.hash(password)

    await db.commit()
    return RedirectResponse("/admin/users?msg=updated", status_code=303)

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
async def activate_user(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user_to_mod = result.scalar_one_or_none()
    
    if user_to_mod:
        user_to_mod.is_active = True # On réactive !
        await db.commit()
        return RedirectResponse("/admin/users?msg=activated", status_code=303)
    
    return RedirectResponse("/admin/users?error=not_found", status_code=303)

# --- EXPORT CSV ---
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
    # 1. Calcul de la période glissante (indispensable pour la cohérence)
    start_val = start_annee * 100 + start_mois
    end_val = end_annee * 100 + end_mois

    # 2. Base de la requête avec OUTERJOIN pour ne rien perdre
    stmt = (
        select(LigneDeclaration, Declaration, User, SousMission, Mission)
        .join(Declaration, LigneDeclaration.declaration_id == Declaration.id)
        .join(User, Declaration.user_id == User.id)
        .join(SousMission, LigneDeclaration.sous_mission_id == SousMission.id)
        .outerjoin(Mission, SousMission.mission_id == Mission.id) # Outerjoin au cas où
    )

    # 3. Application des filtres synchronisés avec le dashboard
    filters = [
        (Declaration.annee * 100 + Declaration.mois) >= start_val,
        (Declaration.annee * 100 + Declaration.mois) <= end_val
    ]

    # --- 2. LOGIQUE DES STATUTS (SÉCURISÉE AU MAXIMUM) ---
    if statut == "validee":
        # On cherche par la valeur texte brute
        filters.append(Declaration.statut.cast(String).like("%validee%"))
    elif statut == "soumise":
        filters.append(Declaration.statut.cast(String).like("%soumise%"))
    else:
        # On prend tout ce qui contient 'validee' OU 'soumise'
        filters.append(
            or_(
                Declaration.statut.cast(String).like("%validee%"),
                Declaration.statut.cast(String).like("%soumise%")
            )
        )

    if programme:
        filters.append(User.programme == programme) # On filtre sur User
    if matiere:
        filters.append(User.matiere == matiere)
    
    # Appliquer tous les filtres
    stmt = stmt.where(and_(*filters))

    # 4. Exécution
    result = await db.execute(stmt)
    rows = result.all()

    # 5. Génération CSV (avec UTF-8-SIG pour Excel)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Mois/Année", "Collaborateur", "Site", "Prog", "Mission", "Sous-Mission", "Quantité", "Total Brut"])

    for ligne_dec, dec, u, sm, m in rows:
        total_ligne = ligne_dec.quantite * sm.tarif
        writer.writerow([
            f"{dec.mois}/{dec.annee}",
            f"{u.prenom} {u.nom}",
            u.site.value if u.site else "N/C",
            u.programme.value if u.programme else "N/C",
            m.titre if m else "N/C", 
            sm.titre,
            str(ligne_dec.quantite).replace('.', ','),
            str(round(total_ligne, 2)).replace('.', ',')
        ])

    filename = f"export_avicenne_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
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
@router.post("/referentiel/mission/add")
async def admin_add_mission(
    request: Request,
    nom: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(catalogue_manager)
):
    new_mission = Mission(titre=nom, ordre=0, is_active=True)
    db.add(new_mission)
    await db.commit()
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

# --- ACTION : AJOUTER SOUS-MISSION ---
@router.post("/referentiel/sub-mission/add")
async def admin_add_sub_mission(
    parent_id: int = Form(...),
    nom: str = Form(...),
    tarif: float = Form(...),
    unite: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(catalogue_manager)
):
    unite_value = unite.strip() if unite else None
    if unite_value and unite_value not in set(UNITES_CHOICES):
        raise HTTPException(status_code=400, detail="Unité invalide")

    new_sm = SousMission(
        mission_id=parent_id,
        titre=nom,
        tarif=tarif,
        unite=unite_value,
        is_active=True
    )
    db.add(new_sm)
    await db.commit()
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(
    request: Request, 
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(check_admin)
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
async def edit_user_post(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(check_admin),
    email: str = Form(...),
    nom: Optional[str] = Form(None),
    prenom: Optional[str] = Form(None),
    role: str = Form(...),
    site: Optional[str] = Form(None),
    filiere: Optional[str] = Form(None),
    annee: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    matiere: Optional[str] = Form(None),
    password: Optional[str] = Form(None)
):
    user_to_update = await db.get(User, user_id)
    if not user_to_update:
        return RedirectResponse(url="/admin/users?error=notfound", status_code=303)

    try:
        # 1. Champs texte
        user_to_update.email = email.lower().strip()
        user_to_update.nom = nom.upper() if nom else None
        user_to_update.prenom = prenom.capitalize() if prenom else None
        user_to_update.matiere = matiere if matiere else None

        # 2. Enums (Conversion sécurisée)
        user_to_update.role = Role(role)
        user_to_update.site = Site(site) if site else None
        user_to_update.filiere = Filiere(filiere) if filiere else None
        user_to_update.annee = Annee(annee) if annee else None
        user_to_update.programme = Programme(programme) if programme else None

        # 3. Mot de passe (Uniquement si rempli)
        if password and len(password.strip()) >= 8:
            user_to_update.hashed_password = pwd_context.hash(password)

        await db.commit()
        return RedirectResponse(url="/admin/users?msg=updated", status_code=303)

    except IntegrityError:
        await db.rollback()
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=email_exists", status_code=303)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Donnée invalide : {str(e)}")
    
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

    # On inverse l'état (True -> False ou False -> True)
    mission.is_active = not mission.is_active

    await db.commit()
    return RedirectResponse(url="/admin/referentiel/missions", status_code=303)