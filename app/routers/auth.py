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
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # 1. Vérification email + mot de passe
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Email ou mot de passe incorrect"},
            status_code=400,
        )

    # 2. VÉRIFICATION DU COMPTE ACTIF (L'ajout est ici)
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ce compte a été désactivé. Veuillez contacter l'administrateur."},
            status_code=403, # Forbidden
        )

    # 3. Création de la session si tout est OK
    token = serializer.dumps({"user_id": user.id})
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=86400 * 7, samesite="lax")
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

    if user and user.is_active:
        # 1. Génération du token (expire après 30 min via le salt dédié)
        token = serializer.dumps(user.email, salt="password-reset-salt")
        
        # 2. Génération de l'URL absolue
        # On force la conversion en str car url_for retourne un objet Datastructures.URL
        reset_link = str(request.url_for("reset_password_page", token=token))
        
        # 3. Envoi de l'email en arrière-plan (ne bloque pas la réponse HTTP)
        # Assure-toi que send_reset_password_email est bien importé
        from app.services.mail import send_reset_password_email
        background_tasks.add_task(send_reset_password_email, user.email, reset_link)
        
        print(f"DEBUG: Tâche d'envoi créée pour {user.email}")

    # 4. Réponse utilisateur (Message générique pour la sécurité)
    return templates.TemplateResponse(
        "forgot_password.html", 
        {
            "request": request, 
            "success": "Si cet email existe, un lien de récupération a été envoyé."
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