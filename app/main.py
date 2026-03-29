from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from datetime import date

# Imports internes
from app.database import get_db, engine, Base
from app.dependencies import get_current_user
from app.models.user import User, Role
from app.models.declaration import Declaration
from app.routers import auth, profile, missions, declarations, admin, users

# DÉFINITION DU LIFESPAN
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code exécuté au démarrage : création des tables si elles n'existent pas
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

# --- CREATION DE L'APPLICATION ---
app = FastAPI(title="Avicenne Pay", lifespan=lifespan)

# --- CONFIGURATION CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION DES STATIQUES ET TEMPLATES ---
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# INJECTION GLOBALE : Rend 'today_day' disponible dans TOUS les templates (base.html, etc.)
# Cela évite les erreurs "today_day is undefined" sans modifier chaque route.
templates.env.globals.update(
    today_day=date.today().day,
    today_month=date.today().month
)

# --- INCLUSION DES ROUTEURS ---
# --- ESPACE ADMINISTRATION ---
# Tout ce qui commence par /admin est réservé à la gestion (Admin/Coordo)
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(users.router, prefix="/admin", tags=["Users Management"])
# app.include_router(missions.router, prefix="/admin", tags=["Missions Management"])

# --- ESPACE UTILISATEUR & COEUR DE MÉTIER ---
# Routes accessibles selon le rôle, mais sans le label "admin" dans l'URL
app.include_router(auth.router, tags=["Authentication"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(declarations.router, prefix="/declarations", tags=["Declarations"])

# --- MIDDLEWARE DE SÉCURITÉ CSP ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    csp_directives = {
        "default-src": "'self'",
        "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
        "style-src": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "style-src-elem": "'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "font-src": "'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
        "connect-src": "'self' https://cdn.jsdelivr.net",
        "img-src": "'self' data: https:"
    }
    
    csp_string = "; ".join([f"{k} {v}" for k, v in csp_directives.items()])
    response.headers["Content-Security-Policy"] = csp_string
    return response

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
    Affiche le tableau de bord avec les dernières déclarations de l'utilisateur.
    """
    stmt = (
        select(Declaration)
        .where(Declaration.user_id == current_user.id)
        .order_by(Declaration.updated_at.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    user_declarations = result.scalars().all()

    # Note : today_day est injecté globalement, pas besoin de l'ajouter ici
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
    # 1. Vérification si l'admin existe déjà
    result = await db.execute(select(User).where(User.role == Role.admin))
    if result.scalar_one_or_none():
        return RedirectResponse("/login", status_code=303)

    if not email or not password:
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": "Email et mot de passe requis"}
        )

    try:
        # 2. Hachage et création
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_context.hash(password)

        admin_user = User(
            email=email, 
            hashed_password=hashed, 
            role=Role.admin,
            is_active=True # Assure-toi que l'admin est actif par défaut
        )
        
        db.add(admin_user)
        await db.commit()
        
        return RedirectResponse("/login?setup=ok", status_code=303)

    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": "Cet email est déjà utilisé."}
    )

    except Exception as e:
        await db.rollback()
        return templates.TemplateResponse(
            "setup.html", 
            {"request": request, "error": f"Erreur interne : {str(e)}"}
    )