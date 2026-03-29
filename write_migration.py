import pathlib, py_compile, sys

TARGET = pathlib.Path("alembic/versions/ce1be1e84b8b_add_declarations.py")

if TARGET.exists():
    TARGET.unlink()
    print(f"Ancien fichier supprimé.")

CONTENT = """\
\"\"\"add_declarations

Revision ID: ce1be1e84b8b
Revises: ff1bee977095
Create Date: 2025-01-01 00:00:00.000000
\"\"\"
from alembic import op

revision = 'ce1be1e84b8b'
down_revision = 'ff1bee977095'
branch_labels = None
depends_on = None


def _run(sql):
    op.get_bind().exec_driver_sql(sql)


def _param(sql, params):
    return op.get_bind().exec_driver_sql(sql, params).fetchone()


def _col_type(table, column):
    row = _param(
        "SELECT udt_name FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return row[0] if row else None


def _col_exists(table, column):
    return _param(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s",
        (table, column),
    ) is not None


def _col_nullable(table, column):
    row = _param(
        "SELECT is_nullable FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return row[0] if row else None


def _table_exists(table):
    return _param(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,),
    ) is not None


def _type_exists(typename):
    return _param(
        "SELECT 1 FROM pg_type WHERE typname = %s",
        (typename,),
    ) is not None


def upgrade():

    # ================================================================
    # ROLE
    # ================================================================
    if _col_type('users', 'role') not in ('text', None):
        _run("ALTER TABLE users ALTER COLUMN role TYPE text USING role::text")
    _run("UPDATE users SET role = 'resp' WHERE role IN ('parrain', 'parrain_marraine')")
    if not _type_exists('role_enum'):
        _run("CREATE TYPE role_enum AS ENUM ('admin','coordo','tcp','top','com','resp')")
    if _col_type('users', 'role') == 'text':
        _run("ALTER TABLE users ALTER COLUMN role TYPE role_enum USING role::role_enum")

    # ================================================================
    # SITE
    # ================================================================
    if _col_type('users', 'site') not in ('text', None):
        _run("ALTER TABLE users ALTER COLUMN site TYPE text USING site::text")
    _run("UPDATE users SET site = 'Lyon Est' WHERE site = 'lyon_est'")
    _run("UPDATE users SET site = 'Lyon Sud' WHERE site = 'lyon_sud'")
    if not _type_exists('site_enum'):
        _run("CREATE TYPE site_enum AS ENUM ('Lyon Est','Lyon Sud')")
    if _col_type('users', 'site') == 'text':
        _run("ALTER TABLE users ALTER COLUMN site TYPE site_enum USING site::site_enum")

    # ================================================================
    # PROGRAMME
    # ================================================================
    if _col_type('users', 'programme') not in ('text', None):
        _run("ALTER TABLE users ALTER COLUMN programme TYPE text USING programme::text")
    _run("UPDATE users SET programme = 'PASS'  WHERE programme = 'pass_'")
    _run("UPDATE users SET programme = 'LAS 1' WHERE programme = 'las1'")
    _run("UPDATE users SET programme = 'LAS 2' WHERE programme = 'las2'")
    if not _type_exists('programme_enum'):
        _run("CREATE TYPE programme_enum AS ENUM ('PASS','LAS 1','LAS 2')")
    if _col_type('users', 'programme') == 'text':
        _run("ALTER TABLE users ALTER COLUMN programme TYPE programme_enum USING programme::programme_enum")

    # ================================================================
    # FILIERE
    # ================================================================
    if _col_type('users', 'filiere') not in ('text', None):
        _run("ALTER TABLE users ALTER COLUMN filiere TYPE text USING filiere::text")
    _run("UPDATE users SET filiere = 'Medecine'   WHERE filiere = 'medecine'")
    _run("UPDATE users SET filiere = 'Pharmacie'  WHERE filiere = 'pharmacie'")
    _run("UPDATE users SET filiere = 'Dentaire'   WHERE filiere = 'dentaire'")
    _run("UPDATE users SET filiere = 'Sage-femme' WHERE filiere = 'sage_femme'")
    _run("UPDATE users SET filiere = 'Kine'       WHERE filiere = 'kine'")
    if not _type_exists('filiere_enum'):
        _run("CREATE TYPE filiere_enum AS ENUM ('Medecine','Pharmacie','Dentaire','Sage-femme','Kine')")
    if _col_type('users', 'filiere') == 'text':
        _run("ALTER TABLE users ALTER COLUMN filiere TYPE filiere_enum USING filiere::filiere_enum")

    # ================================================================
    # ANNEE
    # ================================================================
    if _col_type('users', 'annee') not in ('text', None):
        _run("ALTER TABLE users ALTER COLUMN annee TYPE text USING annee::text")
    _run("UPDATE users SET annee = 'P2' WHERE annee = 'p2'")
    _run("UPDATE users SET annee = 'D1' WHERE annee = 'd1'")
    _run("UPDATE users SET annee = 'D2' WHERE annee = 'd2'")
    _run("UPDATE users SET annee = 'D3' WHERE annee = 'd3'")
    if not _type_exists('annee_enum'):
        _run("CREATE TYPE annee_enum AS ENUM ('P2','D1','D2','D3')")
    if _col_type('users', 'annee') == 'text':
        _run("ALTER TABLE users ALTER COLUMN annee TYPE annee_enum USING annee::annee_enum")

    # ================================================================
    # PROFIL_COMPLETE — suppression
    # ================================================================
    if _col_exists('users', 'profil_complete'):
        _run("ALTER TABLE users DROP COLUMN profil_complete")

    # ================================================================
    # MISSIONS / SOUS_MISSIONS — colonnes updated_at
    # ================================================================
    if not _col_exists('missions', 'updated_at'):
        _run(
            "ALTER TABLE missions ADD COLUMN updated_at"
            " TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL"
        )
    if not _col_exists('sous_missions', 'updated_at'):
        _run(
            "ALTER TABLE sous_missions ADD COLUMN updated_at"
            " TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL"
        )

    # SOUS_MISSIONS.ordre — rendre nullable
    if _col_nullable('sous_missions', 'ordre') == 'NO':
        _run("ALTER TABLE sous_missions ALTER COLUMN ordre DROP NOT NULL")

    # ================================================================
    # ENUM statut_declaration
    # ================================================================
    if not _type_exists('statut_declaration_enum'):
        _run(
            "CREATE TYPE statut_declaration_enum"
            " AS ENUM ('Brouillon','Soumise','Validee','Validation Finale')"
        )

    # ================================================================
    # TABLE declarations
    # ================================================================
    if not _table_exists('declarations'):
        _run(
            "CREATE TABLE declarations ("
            "  id                   SERIAL PRIMARY KEY,"
            "  user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
            "  site                 site_enum NOT NULL,"
            "  programme            programme_enum NOT NULL,"
            "  mois                 INTEGER NOT NULL,"
            "  annee                INTEGER NOT NULL,"
            "  statut               statut_declaration_enum NOT NULL DEFAULT 'Brouillon',"
            "  soumise_le           TIMESTAMP WITHOUT TIME ZONE,"
            "  validee_par_id       INTEGER REFERENCES users(id),"
            "  validee_le           TIMESTAMP WITHOUT TIME ZONE,"
            "  validation_finale_le TIMESTAMP WITHOUT TIME ZONE,"
            "  created_at           TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,"
            "  updated_at           TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,"
            "  CONSTRAINT uq_declaration_user_periode"
            "    UNIQUE (user_id, site, programme, mois, annee)"
            ")"
        )

    # ================================================================
    # TABLE lignes_declaration
    # ================================================================
    if not _table_exists('lignes_declaration'):
        _run(
            "CREATE TABLE lignes_declaration ("
            "  id              SERIAL PRIMARY KEY,"
            "  declaration_id  INTEGER NOT NULL REFERENCES declarations(id) ON DELETE CASCADE,"
            "  sous_mission_id INTEGER NOT NULL REFERENCES sous_missions(id),"
            "  quantite        FLOAT NOT NULL DEFAULT 0,"
            "  montant_calcule FLOAT,"
            "  commentaire     TEXT,"
            "  created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,"
            "  updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL"
            ")"
        )


def downgrade():
    _run("DROP TABLE IF EXISTS lignes_declaration")
    _run("DROP TABLE IF EXISTS declarations")
    _run("DROP TYPE IF EXISTS statut_declaration_enum")
    _run("DROP TYPE IF EXISTS annee_enum")
    _run("DROP TYPE IF EXISTS filiere_enum")
    _run("DROP TYPE IF EXISTS programme_enum")
    _run("DROP TYPE IF EXISTS site_enum")
    _run("DROP TYPE IF EXISTS role_enum")
"""

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(CONTENT, encoding="utf-8")
print(f"Fichier écrit  : {TARGET}")
print(f"Taille         : {TARGET.stat().st_size} octets")

# ── Vérification syntaxe Python ──────────────────────────────────────────────
try:
    py_compile.compile(str(TARGET), doraise=True)
    print("Syntaxe Python : OK")
except py_compile.PyCompileError as e:
    print(f"ERREUR syntaxe : {e}")
    sys.exit(1)

# ── Vérifications contenu ─────────────────────────────────────────────────────
text = TARGET.read_text(encoding="utf-8")
checks = {
    "DO blocks absents"      : ("DO $" not in text and "DO $$" not in text),
    "sa.text() absent"       : ("sa.text" not in text),
    ".execute(sa.) absent"   : (".execute(sa." not in text),
    "exec_driver_sql présent": ("exec_driver_sql" in text),
    "import sa absent"       : ("import sqlalchemy" not in text),
}
all_ok = True
for label, ok in checks.items():
    status = "OK" if ok else "ERREUR !"
    print(f"  {status:8s} {label}")
    if not ok:
        all_ok = False

print(f"\nLignes totales : {text.count(chr(10))}")
print("=" * 40)
print("SUCCÈS — prêt pour alembic upgrade head" if all_ok else "ÉCHEC — corriger avant migration")
