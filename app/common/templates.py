from fastapi.templating import Jinja2Templates
from datetime import date

templates = Jinja2Templates(directory="app/templates")
# On centralise ici toutes les variables globales
templates.env.globals.update(today_day=date.today().day)
