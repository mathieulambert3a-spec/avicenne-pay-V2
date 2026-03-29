# -*- coding: utf-8 -*-
import pathlib

MIGRATION = """\
# -*- coding: utf-8 -*-
\"\"\"init

Revision ID: 0001_init
Revises:
Create Date: 2025-01-01 00:00:00
\"\"\"
from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    def run(sql):
        conn.exec_driver_sql(sql)

    # ENUMS
    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE role_enum AS ENUM (
                'admin','coordo','resp','tcp','top','top_com','com'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE filiere_enum AS ENUM (
                'Medecine','Pharmacie','Maieutique','Odontologie','Kinesitherapie'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE annee_enum AS ENUM (
                'P2','D1','D2'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE site_enum AS ENUM (
                'Lyon Est','Lyon Sud'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE programme_enum AS ENUM (
                'PASS','LAS 1','LAS 2'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE typecontrat_enum AS ENUM (
                'DA','CDDU_PEDA','CDDU_COM'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE unitetype_enum AS ENUM (
                'heure','forfait','journee','demi-journee','etudiant'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE TYPE statutdeclaration_enum AS ENUM (
                'brouillon','soumise','validee','validation_finale'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $BODY$
    \"\"\")

    # TABLE users
    run(\"\"\"CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        email           VARCHAR(255) NOT NULL UNIQUE,
        hashed_password VARCHAR(255) NOT NULL,
        role            role_enum NOT NULL,
        nom             VARCHAR(100),
        prenom          VARCHAR(100),
        adresse         VARCHAR(500),
        code_postal     VARCHAR(10),
        ville           VARCHAR(100),
        telephone       VARCHAR(20),
        nss_encrypted   VARCHAR(500),
        iban_encrypted  VARCHAR(500),
        filiere         filiere_enum,
        annee           annee_enum,
        site            site_enum,
        programme       programme_enum,
        matiere         VARCHAR(100),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )\"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE UNIQUE INDEX uq_resp_site_programme_matiere
            ON users (site, programme, matiere)
            WHERE role = 'resp'
              AND is_active = true
              AND matiere IS NOT NULL;
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $BODY$
    \"\"\")

    run(\"\"\"
        DO $BODY$ BEGIN
            CREATE UNIQUE INDEX uq_top_com_site
            ON users (site)
            WHERE role = 'top_com'
              AND is_active = true;
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $BODY$
    \"\"\")

    # TABLE missions
    run(\"\"\"CREATE TABLE IF NOT EXISTS missions (
        id           SERIAL PRIMARY KEY,
        titre        VARCHAR(500) NOT NULL,
        type_contrat typecontrat_enum NOT NULL DEFAULT 'DA',
        ordre        INTEGER NOT NULL DEFAULT 0,
        is_active    BOOLEAN NOT NULL DEFAULT TRUE,
        resp_only    BOOLEAN NOT NULL DEFAULT FALSE,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )\"\"\")

    # TABLE sous_missions
    run(\"\"\"CREATE TABLE IF NOT EXISTS sous_missions (
        id          SERIAL PRIMARY KEY,
        mission_id  INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
        titre       VARCHAR(500) NOT NULL,
        tarif       FLOAT NOT NULL,
        unite       unitetype_enum NOT NULL DEFAULT 'forfait',
        ordre       INTEGER,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_sous_mission_tarif_positif CHECK (tarif >= 0)
    )\"\"\")

    # TABLE user_sous_mission_permissions
    run(\"\"\"CREATE TABLE IF NOT EXISTS user_sous_mission_permissions (
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sous_mission_id INTEGER NOT NULL REFERENCES sous_missions(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, sous_mission_id)
    )\"\"\")

    # TABLE declarations
    run(\"\"\"CREATE TABLE IF NOT EXISTS declarations (
        id                   SERIAL PRIMARY KEY,
        user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        validee_par_id       INTEGER REFERENCES users(id),
        site                 site_enum NOT NULL,
        programme            programme_enum NOT NULL,
        mois                 INTEGER NOT NULL,
        annee                INTEGER NOT NULL,
        statut               statutdeclaration_enum NOT NULL DEFAULT 'brouillon',
        commentaire_admin    VARCHAR(500),
        soumise_le           TIMESTAMPTZ,
        validee_le           TIMESTAMPTZ,
        validation_finale_le TIMESTAMPTZ,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_declaration_mois_valide  CHECK (mois >= 1 AND mois <= 12),
        CONSTRAINT ck_declaration_annee_valide CHECK (annee >= 2020 AND annee <= 2100),
        CONSTRAINT uq_declaration_user_periode UNIQUE (user_id, site, programme, mois, annee)
    )\"\"\")

    # TABLE lignes_declaration
    run(\"\"\"CREATE TABLE IF NOT EXISTS lignes_declaration (
        id              SERIAL PRIMARY KEY,
        declaration_id  INTEGER NOT NULL REFERENCES declarations(id) ON DELETE CASCADE,
        sous_mission_id INTEGER NOT NULL REFERENCES sous_missions(id),
        quantite        FLOAT NOT NULL,
        montant_calcule FLOAT,
        CONSTRAINT ck_ligne_quantite_positive CHECK (quantite > 0)
    )\"\"\")


def downgrade():
    conn = op.get_bind()

    def run(sql):
        conn.exec_driver_sql(sql)

    run("DROP TABLE IF EXISTS lignes_declaration CASCADE")
    run("DROP TABLE IF EXISTS declarations CASCADE")
    run("DROP TABLE IF EXISTS user_sous_mission_permissions CASCADE")
    run("DROP TABLE IF EXISTS sous_missions CASCADE")
    run("DROP TABLE IF EXISTS missions CASCADE")
    run("DROP TABLE IF EXISTS users CASCADE")
    run("DROP TYPE IF EXISTS statutdeclaration_enum")
    run("DROP TYPE IF EXISTS unitetype_enum")
    run("DROP TYPE IF EXISTS typecontrat_enum")
    run("DROP TYPE IF EXISTS programme_enum")
    run("DROP TYPE IF EXISTS site_enum")
    run("DROP TYPE IF EXISTS annee_enum")
    run("DROP TYPE IF EXISTS filiere_enum")
    run("DROP TYPE IF EXISTS role_enum")
"""

out = pathlib.Path("alembic/versions/0001_init.py")
out.write_text(MIGRATION, encoding="utf-8")
print(f"OK — {out.stat().st_size} octets")

text = out.read_text(encoding="utf-8")
assert "$$" not in text or "$BODY$" in text, "ERREUR: $$ nu detecte!"
assert "%s" not in text, "ERREUR: %s present!"
assert "head BEGIN" not in text, "ERREUR: head BEGIN detecte!"
print("Verification OK")
