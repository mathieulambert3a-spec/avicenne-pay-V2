# 📄 Cahier des Charges Fonctionnel - Avicenne Pay

## 1. Présentation du Projet
* **Application :** Avicenne Pay
* **Directeur Général :** Mathieu LAMBERT
* **Contexte :** Gestion administrative et financière d'une prépa santé sur 2 sites (Lyon Est, Lyon Sud) comptant environ 300 apprenants et une équipe d'étudiants encadrants (P2 à D1).
* **Objectif :** Automatiser la déclaration des missions, le circuit de validation hiérarchique et la génération des exports comptables.

---

## 2. Architecture Technique & Dépendances
L'application repose sur la stack Python suivante :
* **Framework :** `fastapi`, `uvicorn[standard]`
* **ORM & Base de données :** `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `psycopg2-binary`
* **Sécurité & Chiffrement :** `passlib[bcrypt]`, `cryptography`, `itsdangerous`
* **Templating & Validation :** `jinja2`, `python-multipart`, `python-dotenv`

---

## 3. Architecture des Rôles et Périmètres

### 3.1 Matrice des Droits (Role Enum)
* **admin** : Accès global, gestion des utilisateurs, statistiques, référentiel missions et validation finale.
* **coordo** : Gestion d'un site (Lyon Est ou Sud), affectation des missions, validation N+1.
* **resp** : Référent d'une matière/programme sur un site. Gère ses TCP et valide leurs déclarations.
* **tcp** : Intervenant réalisant les missions. Saisie et soumission de ses déclarations.

### 3.2 Détails des Périmètres
* **Sites :** Lyon Est, Lyon Sud.
* **Filières :** Médecine, Pharmacie, Maïeutique, Odontologie, Kinésithérapie.
* **Années :** P2 (2ème année), D1 (3ème année).
* **Programmes & Matières :**
    * **PASS** : UE_1 à UE_8, MMOK, PHARMA, Min SVE, Min SVH, Min SPS, Min EEEA, Min PHY_MECA, Min MATH, Min CHIMIE, Min STAPS, Min DROIT, ORAUX.
    * **LAS 1** : Physiologie, Anatomie, Biologie Cell, Biochimie, Biostats, Biophysique, Chimie, SSH, Santé Publique, ICM, HBDV.
    * **LAS 2** : Microbiologie, Biocell / Immuno, Biologie Dev, Enzmo / Métabo, Génétique, Physiologie, Statistiques, MES GSE.

---

## 4. Logique Métier et Rémunération

### 4.1 Coût Chargé
* **Cession de Droits d'Auteur (RESP & TCP) :** Coefficient de **1,2**.
* **Calcul :** $$Total\ Chargé = Brut \times 1,2$$

### 4.2 Référentiel Intégral des Missions (Catalogue)

| Catégorie | Mission / Titre | Tarif | Unité |
| :--- | :--- | :--- | :--- |
| **✍️ Rédiger supports** | LVL 1 - Pas/peu de changements (1p max) | 10.0 | par map / support |
| | LVL 2 - Changements moyens (2-3p) | 25.0 | par map / support |
| | LVL 3 - Beaucoup de changements (4p+) | 50.0 | par map / support |
| | LVL 4 - Création de novo | 100.0 | par map / support |
| | LVL 5 - De novo long/difficile (>30p) - UE1 | 200.0 | par map / support |
| **🎙️ Enregistrement** | Enregistrer et réécouter le cours | 10.0 | par heure |
| **📚 Création entraînements**| LVL 1 - Questions de cours simples | 3.0 | par qcm |
| | LVL 2 - Intermédiaire (énoncé long/schéma) | 4.0 | par qcm |
| | LVL 3 - Questions d'exercice | 6.0 | par qcm |
| | LVL 4 - Exercice complexe (UE2, 3, 6) | 8.0 | par qcm |
| **📖 Annales** | Relecture des annales (si nécessaire) | 10.0 | par annale / année |
| | **Correction** LVL 1 - Questions de cours | 1.5 | par qcm |
| | **Correction** LVL 2 - Intermédiaire | 2.0 | par qcm |
| | **Correction** LVL 3 - Exercice | 3.0 | par qcm |
| **👨‍🏫 Animation & Suivi** | Supports existants (ED, TD, SPR, TDR) | 12.0 | par heure |
| | Supports à créer (ED, TD, SPR, TDR) | 24.0 | par heure |
| | Permanences / Support forum (séance 2h) | 10.0 | par heure |
| **📝 Relecture & Mise en page**| LVL 1 - Peu de changements (1p max) | 3.0 | par support |
| | LVL 2 - Changements moyens (2-3p) | 5.0 | par support |
| | LVL 3 - Beaucoup de changements (4p+) | 10.0 | par support |
| | LVL 4 - Support créé de novo | 20.0 | par support |
| | LVL 5 - De novo >30p (UE2, 3, 6) | 30.0 | par support |
| | LVL 6 - De novo >30p (UE1) | 50.0 | par support |
| **💻 Théia (Intégration)** | Standard (Classique, images, texte) | 0.5 | par qcm |
| | Complexe (Formules mathématiques UE3/6) | 1.0 | par qcm |
| **👔 Gestion & Divers** | Gestion d'équipe (Réunions, suivi mensuel) | 50.0 | par mois |
| | Réunion de formation (Word, Teams...) | 50.0 | par jour |
| | Participation réunions pré-colles | 10.0 | par pré-colle |
| | Création Post-it de novo | 50.0 | par post-it |
| **☀️ Été** | Mise à jour estivale (Semaine complète) | 300.0 | par semaine |

### 4.3 Unités autorisées (`UNITES_CHOICES`)
* **Temps :** par heure, par jour, par mois, par séance.
* **Volume :** par qcm, par annale et par année, par post-it, par support / map.
* **Forfait :** forfait mise à jour estivale, par pré-colle.

---

## 5. Workflow de Validation
Le cycle de vie d'une déclaration :
1.  **Brouillon** : Saisie utilisateur.
2.  **Soumise** : En attente du N+1 (RESP ou COORDO).
3.  **Validée (Intermédiaire)** : Validée par le N+1.
4.  **Validation Finale** : Approuvée par l'ADMIN (Export comptable).

> **Règle de rejet :** Tout refus nécessite un **commentaire obligatoire** et renvoie la déclaration en **Brouillon**.

---

## 6. Modèle de Données et Schémas (Pydantic/SQLAlchemy)

### 6.1 Utilisateur (Table `users`)
Inclut les informations personnelles et les données sensibles chiffrées (`nss_encrypted`, `iban_encrypted`).

### 6.2 Schémas de Sortie (API)
* **DeclarationOut** : Inclut l'ID, le mois/année, le statut, les lignes de missions et le `total_montant` calculé.
* **LigneDeclarationOut** : Détaille la mission liée (quantité, titre, unité).
* **UserUpdate** : Permet la mise à jour du profil (adresse, tel, IBAN, NSS, affectation académique).