from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import BackgroundTasks
from itsdangerous import URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import SECRET_KEY
from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user_optional
from app.services.mail import send_reset_password_email
from app.common.templates import templates


router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Recherche de l'utilisateur par email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # 1. VÉRIFICATION IDENTIFIANTS
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Email ou mot de passe incorrect"},
            status_code=400,
        )

    # 2. VÉRIFICATION DU RÔLE (Règle : Les Parrains n'ont aucun accès)
    from app.models.user import Role # Assure-toi que l'import est correct
    if user.role == Role.parrain_marraine:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ce profil n'est pas autorisé à se connecter à l'application."},
            status_code=403,
        )

    # 3. VÉRIFICATION DU COMPTE ACTIF
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ce compte a été désactivé. Veuillez contacter l'administrateur."},
            status_code=403,
        )

    # 4. CRÉATION DE LA SESSION (Si toutes les étapes précédentes ont réussi)
    token = serializer.dumps({"user_id": user.id})
    response = RedirectResponse("/dashboard", status_code=302)
    
    # Cookie sécurisé pour 7 jours
    response.set_cookie(
        "session", 
        token, 
        httponly=True, 
        max_age=86400 * 7, 
        samesite="lax",
        secure=True
    ) 
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response

# --- ROUTES MOT DE PASSE OUBLIÉ ---
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Recherche de l'utilisateur
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    from app.models.user import Role # Import du modèle Role

    # On n'envoie l'email QUE si l'utilisateur :
    # 1. Existe
    # 2. Est actif
    # 3. N'EST PAS un parrain/marraine (car ils n'ont pas d'accès interface)
    if user and user.is_active and user.role != Role.parrain_marraine:
        
        # 1. Génération du token
        token = serializer.dumps(user.email, salt="password-reset-salt")
        
        # 2. Génération de l'URL absolue
        reset_link = str(request.url_for("reset_password_page", token=token))
        
        # 3. Envoi de l'email en arrière-plan
        from app.services.mail import send_reset_password_email
        background_tasks.add_task(send_reset_password_email, user.email, reset_link)
        
        print(f"DEBUG: Tâche d'envoi créée pour {user.email}")

    # 4. Réponse utilisateur (On garde le message générique même si c'est un parrain, pour la sécurité)
    return templates.TemplateResponse(
        "forgot_password.html", 
        {
            "request": request, 
            "success": "Si cet email correspond à un compte actif, un lien de récupération a été envoyé."
        }
    )

@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    try:
        # On vérifie si le token est valide ET s'il a moins de 30 minutes (1800s)
        email = serializer.loads(token, salt="password-reset-salt", max_age=1800)
        return templates.TemplateResponse("reset_password_form.html", {"request": request, "token": token})
    except Exception:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Le lien est invalide ou a expiré."}, 
            status_code=400
        )

@router.post("/reset-password/{token}")
async def reset_password(
    request: Request,
    token: str,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "reset_password_form.html", 
            {"request": request, "token": token, "error": "Les mots de passe ne correspondent pas."}
        )

    try:
        email = serializer.loads(token, salt="password-reset-salt", max_age=1800)
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = pwd_context.hash(new_password)
            await db.commit()
            return RedirectResponse("/login?msg=updated", status_code=302)
            
    except Exception:
        pass # Géré par l'erreur générique ci-dessous

    return RedirectResponse("/login?error=Lien+invalide", status_code=302)