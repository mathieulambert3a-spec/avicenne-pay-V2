import psycopg2

DATABASE_URL = "postgresql://neondb_owner:npg_f9WkjbtyYql1@ep-broad-snow-ab4qbg5r-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require"

def cleanup():
    MY_EMAIL = "superadmin@avicenne.fr"
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print("🧹 Nettoyage de Neon en cours...")
        
        # Supprime les déclarations d'abord (clé étrangère)
        cur.execute("DELETE FROM declarations;")
        # Supprime les utilisateurs sauf l'admin principal
        cur.execute("DELETE FROM users WHERE email != %s;", (MY_EMAIL,))
        
        conn.commit()
        print(f"✅ Nettoyage terminé. {cur.rowcount} utilisateurs supprimés.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    cleanup()