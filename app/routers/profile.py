from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.config import FERNET_KEY
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, Filiere, Annee, Site, Programme, MATIERES
from app.common.templates import templates

router = APIRouter()

def get_fernet():
    if FERNET_KEY:
        return Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
    return None


def encrypt(value: str, f: Optional[Fernet]) -> str:
    if f and value:
        return f.encrypt(value.encode()).decode()
    return value


def decrypt(value: str, f: Optional[Fernet]) -> str:
    if f and value:
        try:
            return f.decrypt(value.encode()).decode()
        except (InvalidToken, Exception):
            return value
    return value or ""


@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: User = Depends(get_current_user)):
    f = get_fernet()
    nss = decrypt(current_user.nss_encrypted or "", f)
    iban = decrypt(current_user.iban_encrypted or "", f)
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "nss": nss,
            "iban": iban,
            "filieres": list(Filiere),
            "annees": list(Annee),
            "sites": list(Site),
            "programmes": list(Programme),
            "matieres": MATIERES,
        },
    )


@router.post("", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    nom: str = Form(""),
    prenom: str = Form(""),
    adresse: str = Form(""),
    code_postal: str = Form(""),
    ville: str = Form(""),
    telephone: str = Form(""),
    nss: str = Form(""),
    iban: str = Form(""),
    filiere: str = Form(""),
    annee: str = Form(""),
    site: str = Form(""),
    programme: str = Form(""),
    matiere: str = Form(""),
    profil_complete: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = get_fernet()
    
    # --- 1. Mise à jour des informations de base (Avec formatage) ---
    if nom: current_user.nom = nom.strip().upper()
    if prenom: current_user.prenom = prenom.strip().capitalize()
    if adresse: current_user.adresse = adresse.strip()
    if code_postal: current_user.code_postal = code_postal.strip()
    if ville: current_user.ville = ville.strip().upper()
    if telephone: current_user.telephone = telephone.strip()

    # --- 2. Données sensibles (NETTOYAGE JS ET CHIFFREMENT) ---
    if nss:
        # On retire les espaces et les barres "|" ajoutés par le masque de saisie JS
        clean_nss = nss.replace(" ", "").replace("|", "")
        current_user.nss_encrypted = encrypt(clean_nss, f)
    else:
        pass
        
    if iban:
        # On retire les espaces du JS et on force les majuscules
        clean_iban = iban.replace(" ", "").upper()
        current_user.iban_encrypted = encrypt(clean_iban, f)

    # --- 3. Affectations Académiques (SÉCURISÉES) ---
    if current_user.role.value in ['admin', 'coordo']:
        if site:
            try: current_user.site = Site(site)
            except ValueError: pass
        if programme:
            try: current_user.programme = Programme(programme)
            except ValueError: pass
            current_user.matiere = matiere or None

    # --- 4. Autres infos académiques (Libres pour RESP/TCP) ---
    if filiere:
        try: current_user.filiere = Filiere(filiere)
        except ValueError: pass
    if annee:
        try: current_user.annee = Annee(annee)
        except ValueError: pass

    # --- [JUSTE AVANT LE BLOC 5] Préparation du dictionnaire de contexte ---
    # On le prépare ici pour pouvoir le réutiliser en cas d'erreur ou de succès
    nss_display = decrypt(current_user.nss_encrypted or "", f)
    iban_display = decrypt(current_user.iban_encrypted or "", f)

    context = {
        "request": request,
        "user": current_user,
        "nss": nss_display,
        "iban": iban_display,
        "filieres": list(Filiere),
        "annees": list(Annee),
        "sites": list(Site),
        "programmes": list(Programme),
        "matieres": MATIERES,
    }
    # --- 5. Statut de complétude ---
    success_msg = "Profil mis à jour avec succès."
    
    # --- 5. Statut de complétude & Sauvegarde ---
    # On calcule la complétude réelle basée sur les données qui viennent d'être injectées
    is_really_complete = current_user.is_payment_profile_complete_logic
    
    if profil_complete == "on":
        # Si l'utilisateur a cliqué sur "Valider et finaliser"
        if is_really_complete:
            current_user.profil_complete = True
            success_msg = "Félicitations ! Votre profil est désormais complet et validé."
        else:
            current_user.profil_complete = False
            # On affine le message d'erreur selon ce qui manque
            if current_user.role.value in ['resp', 'tcp'] and not (current_user.nss_encrypted and current_user.iban_encrypted):
                success_msg = "Profil sauvegardé, mais incomplet : les informations de paiement (NSS/IBAN) sont obligatoires."
            else:
                success_msg = "Profil sauvegardé, mais incomplet : veuillez vérifier votre identité (Nom, Prénom, Ville)."
    else:
        # Si c'est une mise à jour "classique" (Admin ou profil déjà validé)
        # On s'assure que si l'utilisateur vide un champ obligatoire, le statut 'profil_complete' repasse à False
        if current_user.profil_complete and not is_really_complete:
            current_user.profil_complete = False
            success_msg = "Modifications enregistrées. Attention : votre profil n'est plus considéré comme complet."
        else:
            success_msg = "Profil mis à jour avec succès."

    # Sauvegarde finale en base de données
    try:
        await db.commit()
        await db.refresh(current_user)
    except Exception as e:
        await db.rollback()
        # On pourrait logger l'erreur ici
        return templates.TemplateResponse(
            "profile.html", 
            {**context, "error": "Erreur lors de la sauvegarde. Veuillez réessayer."}
        )

    await db.commit()
    await db.refresh(current_user)

    # Préparation du déchiffrement pour l'affichage post-enregistrement
    nss_display = decrypt(current_user.nss_encrypted or "", f)
    iban_display = decrypt(current_user.iban_encrypted or "", f)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "nss": nss_display,
            "iban": iban_display,
            "filieres": list(Filiere),
            "annees": list(Annee),
            "sites": list(Site),
            "programmes": list(Programme),
            "matieres": MATIERES,
            "success": success_msg,
        },
    )