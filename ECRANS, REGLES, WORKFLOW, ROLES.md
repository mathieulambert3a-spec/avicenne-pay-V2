# Récapitulatif exhaustif — Avicenne Pay (écrans, règles, workflow, rôles)

Date : 2026-03-03

## 1) Objectif de l’application
**Avicenne Pay** est une application web (FastAPI) destinée à **automatiser** :
- la **déclaration mensuelle** de missions (TCP + RESP),
- le **circuit de validation hiérarchique** (RESP/COORDO/ADMIN),
- le calcul des montants (notamment “chargé”),
- la **génération d’exports comptables CSV** (détaillé plus tard),
- à terme : **pilotage/statistiques** et **génération de factures PDF**.

Contexte : 2 sites (Lyon Est / Lyon Sud), ~300 apprenants, encadrants P2→D1.

---

## 2) Rôles, périmètres et rattachements

### Rôles
- **admin** : accès global, gestion utilisateurs, stats/pilotage, catalogue missions, **validation finale**, exports, factures, seul à pouvoir déchiffrer les données sensibles des autres.
- **coordo** : gestion d’un **site**, peut gérer catalogue missions, peut valider/survalider selon cas.
- **resp** : rattaché à **1 site**, **1 programme**, **1 matière**. Déclare ses propres missions + valide celles de ses TCP.
- **tcp** : rattaché à **0 ou 1 RESP** (cas “sans RESP” autorisé), et donc à 1 site via la chaîne (RESP→COORDO) ou directement par le site.

### Règles de rattachement (structure)
- Un **TCP dépend d’un seul RESP** (donc **un seul** programme + matière).
- Un **RESP** ne gère qu’**un seul** programme + matière.
- Un **RESP** est rattaché à un **COORDO** via le **site**.
- Un **TCP** hérite du site via son RESP ; mais il existe aussi le cas **TCP sans RESP**, validé par COORDO.

### Référentiels académiques
- **Sites** : Lyon Est, Lyon Sud
- **Filières** : Médecine, Pharmacie, Maïeutique, Odontologie, Kinésithérapie
- **Programmes** : PASS, LAS1, LAS2
- **Matières** : liste **dynamique** dépendant du programme choisi (PASS ≠ LAS1 ≠ LAS2)

---

## 3) Profil utilisateur (“Mon profil”) — règles

### COORDO (profil)
- doit renseigner **uniquement** : **Site** (dropdown Lyon Est / Lyon Sud)
- pas de NSS/IBAN

### TCP & RESP (profil)
- doivent pouvoir renseigner :
  - **Filière** (dropdown)
  - **Programme** (dropdown PASS/LAS1/LAS2)
  - **Matière** (dropdown dynamique selon programme)
  - **IBAN** + **NSS** (leurs propres données)

### Accès / déchiffrement données sensibles
- **Admin** : peut déchiffrer (nécessaire factures + exports)
- **RESP/TCP** : accès à **leurs propres** NSS/IBAN (affichage/édition)
- **Coordo** : pas de besoin d’accès aux données sensibles des autres

---

## 4) Déclarations : règles métier
- Une **déclaration est mensuelle** : couple (**mois**, **année**).
- **Une seule déclaration par mois** et par déclarant (TCP ou RESP).
- Il existe une page explicite : **“Créer la déclaration de <mois> <année>”**.
- **Deadline** : “5 jours avant la fin du mois” = **rappel / message**, **pas un blocage** (on peut toujours soumettre/valider après).

---

## 5) Catalogue des missions (référentiel)
- Catalogue “Missions & sous-missions” (tel que défini dans le CDC) avec tarif + unité.
- Unités autorisées (temps/volume/forfait).
- **Admin et COORDO** peuvent **ajouter / supprimer / modifier** une mission et ses sous-missions.

---

## 6) Calculs / montants
- Coefficient de coût chargé (cession droits d’auteur) : **1,2** (RESP & TCP)
  - `Total chargé = Brut × 1,2`
- **Restriction UI** : le **total brut n’est pas affiché côté TCP** (réservé admin / pilotage ultérieur).  
  (Le “chargé” peut rester affichable si souhaité ; sinon on peut masquer aussi.)

---

## 7) Workflow des statuts (avec COORDO “Validé site”)

### Statuts de cycle de vie d’une déclaration
1. **Brouillon**
   - création/édition par le déclarant (TCP ou RESP)

2. **Soumise**
   - déclenchée par action “Soumettre”

3. **Validée intermédiaire**
   - validée N+1 :
     - par **RESP** pour ses TCP rattachés
     - ou par **COORDO** si **TCP sans RESP**

4. **Validé site**
   - **survalidation** par **COORDO**
   - concerne :
     - les déclarations des TCP passées par un RESP (validées intermédiaire par RESP)
     - les déclarations des **RESP** (après étape intermédiaire)

5. **Validation finale**
   - validation par **ADMIN**
   - condition d’éligibilité typique : statut **Validé site**

### Règle de refus (globale)
- À n’importe quelle étape de validation :
  - **commentaire obligatoire**
  - retour au statut **Brouillon** (ré-éditable et re-soumettable)

---

## 8) Écrans / pages par rôle (exhaustif)

### A) Tronc commun (tous rôles)
- Connexion
- (Optionnel) Mot de passe oublié / reset
- Dashboard (contenu adapté au rôle)
- Mon profil (variantes selon rôle ci-dessus)
- Changer mot de passe
- Déconnexion
- 403 / 404

---

### B) TCP — écrans
- **Dashboard TCP**
  - statut déclaration du mois, alertes (dont rappel J-5), retours de refus
  - pas d’affichage “total brut”
- **Mes déclarations** (liste mois/année, statuts)
- **Créer déclaration (mois/année)** : “Créer la déclaration de Février 2026”
- **Détail / édition déclaration**
  - gestion lignes de missions (ajouter/modifier/supprimer)
  - affichage statut + commentaires de refus
- **Soumettre la déclaration** (action depuis le détail)

---

### C) RESP — écrans (déclarant + valideur)

#### Volet “mes déclarations” (comme TCP)
- Dashboard RESP (bloc “mes déclarations”)
- **Mes déclarations** (RESP)
- **Créer déclaration (mois/année)** (RESP)
- **Détail / édition de sa déclaration**
- **Soumettre sa déclaration**

#### Volet “validation TCP”
- Dashboard RESP (bloc “à valider”)
- **Déclarations TCP à valider** (liste)
- **Détail déclaration TCP** (valider/refuser + commentaire)
- **Historique validations** (optionnel mais recommandé)

---

### D) COORDO — écrans (site + validation + survalidation + référentiels)
- **Dashboard COORDO (site)**
  - compteurs, alertes J-5 (message)
- **Validations (N+1 COORDO)**
  - file : déclarations **Soumises** de **TCP sans RESP**
  - actions : valider → **Validée intermédiaire**, refuser → **Brouillon**
- **Survalidations (site)**
  - file : déclarations **Validée intermédiaire** (validées par RESP + déclarations RESP à survalider)
  - actions : valider → **Validé site**, refuser → **Brouillon**
- **Gestion utilisateurs (site)**
  - création/invitation (si prévu)
  - affectations (RESP : programme+matière uniques ; TCP : RESP unique ou “sans RESP”)
- **Gestion Missions & sous-missions** (CRUD)
- **Suivi mensuel (site)** (consolidation)
- **Mon profil COORDO** (site uniquement)

---

### E) ADMIN — écrans
- **Dashboard ADMIN**
- **Gestion utilisateurs (global)** + affectations
- **Gestion Missions & sous-missions** (CRUD global)
- **Déclarations (vue globale)** (recherche/filtre)
- **Validation finale**
  - file : déclarations **Validé site**
  - actions : valider final → **Validation finale**, refuser → **Brouillon**
- **Exports CSV**
  - (format à préciser plus tard)
- **Pilotage** (stats, vue globale — à développer plus tard mais entrée prévue)
- **Générer factures**
  - saisie période : **date début / date fin**
  - génère **PDF** pour toutes les déclarations **validées final admin** dans la période
  - si période couvre plusieurs mois : **1 facture regroupée** par personne (somme des déclarations)
  - téléchargement d’un **ZIP** contenant tous les PDFs

---

## 9) Menus (proposition cohérente)
- **TCP** : Dashboard / Mes déclarations / Créer déclaration / Mon profil
- **RESP** : Dashboard / Mes déclarations / Créer déclaration / À valider (TCP) / Mon profil
- **COORDO** : Dashboard / Validations / Survalidations / Utilisateurs / Missions / Suivi / Mon profil
- **ADMIN** : Dashboard / Validation finale / Déclarations / Exports / Générer factures / Pilotage / Utilisateurs / Missions / Mon profil