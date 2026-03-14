import asyncio
import datetime
from sqlalchemy import select
from app.database import AsyncSessionLocal # Correction faite précédemment
from app.models.user import User, Role
from app.models.declaration import Declaration, StatutDeclaration
from app.services.mail import FastMail, MessageSchema, MessageType, conf

async def send_reminder_email(email_to, first_name, month_fr):
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px;">
        <h2 style="color: #dc3545;">Rappel Déclaration - Avicenne Pay</h2>
        <p>Bonjour {first_name},</p>
        <p>Sauf erreur de notre part, vous n'avez pas encore validé votre déclaration d'activité pour le mois de <strong>{month_fr}</strong>.</p>
        <p>Nous vous rappelons que la date limite de saisie approche (J-5).</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="http://127.0.0.1:8000/declarations" style="background-color: #dc3545; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Remplir ma déclaration</a>
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

async def main():
    async with AsyncSessionLocal() as db:
        today = datetime.date.today()
        months_fr = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", 
                     "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        current_month_name = months_fr[today.month]

        # 1. Récupérer les utilisateurs (on exclut les admins)
        result = await db.execute(
            select(User).where(
                User.is_active == True,
                User.role.notin_([Role.admin, Role.coordo])
            )
        )
        
        users = result.scalars().all()
        for user in users:
            # On considère que si c'est en "brouillon", il faut quand même relancer
            decl_check = await db.execute(
                select(Declaration).where(
                    Declaration.user_id == user.id,
                    Declaration.mois == today.month,  # Champ 'mois' de ton modèle
                    Declaration.annee == today.year, # Champ 'annee' de ton modèle
                    Declaration.statut != StatutDeclaration.brouillon # Relance si seulement brouillon ou absent
                )
            )

            if not decl_check.scalar_one_or_none():
                print(f"📧 Envoi de la relance à {user.email}...")
                try:
                    await send_reminder_email(user.email, user.prenom, current_month_name)
                    await asyncio.sleep(1.2)
                except Exception as e:
                    print(f"❌ Erreur pour {user.email}: {e}")

if __name__ == "__main__":  
    asyncio.run(main())