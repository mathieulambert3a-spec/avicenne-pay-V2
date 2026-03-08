from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Form
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

# Imports internes
from app.database import get_db, engine, Base
from app.config import SECRET_KEY
from app.dependencies import get_current_user, get_current_user_optional
from app.models.user import User, Role
from app.models.declaration import Declaration
from app.routers import auth, profile, missions, declarations, admin, users
from app.models.mission import Mission
from app.models.sub_mission import SousMission

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code exécuté au démarrage
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Avicenne Pay", lifespan=lifespan)

# MONTAGE LES STATIQUES
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Inclusion des routeurs
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(missions.router)
app.include_router(declarations.router)
app.include_router(admin.router)
app.include_router(users.router)

# --- ROUTES PRINCIPALES ---

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Affiche le tableau de bord avec les notifications de l'administration.
    """
    # Récupération des 5 dernières déclarations pour afficher les statuts et commentaires
    stmt = (
        select(Declaration)
        .where(Declaration.user_id == current_user.id)
        .order_by(Declaration.updated_at.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    user_declarations = result.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, 
            "user": current_user, 
            "declarations": user_declarations
        }
    )

# --- CONFIGURATION INITIALE (SETUP) ---
@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.role == Role.admin))
    admin_exists = result.scalar_one_or_none()
    if admin_exists:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("setup.html", {"request": request})

@app.post("/setup")
async def setup_create_admin(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Vérification de sécurité (si l'admin existe déjà)
    result = await db.execute(select(User).where(User.role == Role.admin))
    if result.scalar_one_or_none():
        return RedirectResponse("/login", status_code=303) # 303 est préférable pour les redirections POST

    # 2. Validation basique (déjà en partie gérée par le Form(...) de FastAPI)
    if not email or not password:
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": "Email et mot de passe requis"}
        )

    try:
        # 3. Hachage du mot de passe
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_context.hash(password)

        # 4. Création de l'utilisateur admin
        admin_user = User(
            email=email, 
            hashed_password=hashed, 
            role=Role.admin
        )
        
        db.add(admin_user)
        await db.commit()
        
        return RedirectResponse("/login?setup=ok", status_code=303)

    except IntegrityError:
        # En cas de doublon d'email ou autre contrainte DB
        await db.rollback()
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": "Cet email est déjà utilisé ou une erreur est survenue."}
        )
    except Exception as e:
        await db.rollback()
        print(f"Erreur lors du setup: {e}")
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": "Une erreur interne est survenue."}
        )