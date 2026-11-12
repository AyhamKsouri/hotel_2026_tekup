# Grand Hôtel — système de gestion d'hôtel

Application web Django + PostgreSQL qui centralise la gestion d'un ou plusieurs hôtels : réservations en ligne,
réception, factures, ménage, cuisine et administration. Projet de groupe 2026/2027 (méthode Scrum, voir
`docs/jira_backlog.csv`).

## Rôles

| Rôle | E-mail du compte | Ce qu'il fait |
|---|---|---|
| Administrateur | `...@admin.com` | Crée ses hôtels (assistant en 3 étapes), gère les utilisateurs, événements et chambres |
| Réceptionniste | `...@service.com` | Gère **son** hôtel : réservations, clients, factures, disponibilité, ménage |
| Agent de nettoyage | `...@service.com` | Chambres à nettoyer / nettoyées, rappels à l'heure prévue |
| Chef cuisinier | `...@service.com` | Menu du jour, stock (légumes, fruits, viande) |
| Client | `...@booking.com` | Parcourt les hôtels, réserve, suit ses réservations et factures |

Connexion par **e-mail ou CIN** + mot de passe, dans l'espace de son rôle (`/espace/client/`, `/espace/admin/`,
`/espace/reception/`, `/espace/nettoyage/`, `/espace/cuisine/`).

## Installation

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/macOS : source venv/bin/activate)
pip install -r requirements.txt
```

### Base de données

Par défaut l'application utilise PostgreSQL. Les valeurs par défaut sont dans `hotel/settings.py`
(base `hoteldb`, utilisateur `postgres`, hôte `localhost`, **port `5433`**). Adaptez-les à votre machine avec
des variables d'environnement plutôt qu'en modifiant le fichier :

| Variable | Rôle |
|---|---|
| `DB_NAME` | nom de la base (défaut `hoteldb`) |
| `DB_USER` | utilisateur PostgreSQL |
| `DB_PASSWORD` | mot de passe PostgreSQL |
| `DB_HOST` | hôte (défaut `localhost`) |
| `DB_PORT` | port (défaut `5433` ; l'installation standard de PostgreSQL utilise `5432`) |

```bash
psql -U postgres -c "CREATE DATABASE hoteldb;"
```

Pour essayer rapidement sans PostgreSQL, utilisez SQLite : `USE_SQLITE=1`
(PowerShell : `$env:USE_SQLITE="1"`).

### Lancer

```bash
python manage.py migrate
python manage.py createsuperuser      # l'e-mail doit se terminer par @admin.com
python manage.py runserver
```

Ouvrir <http://127.0.0.1:8000/>.

### Tests

```bash
python manage.py test                 # avec SQLite : USE_SQLITE=1 python manage.py test
```

`account/test_crawl.py` parcourt l'application avec chaque rôle : il ouvre toutes les pages atteignables et
envoie chaque formulaire / bouton, et échoue si une page plante, affiche du code de gabarit brut ou du texte mal
encodé. `account/test_security.py` rejoue les failles corrigées (inscription admin, prise de contrôle de comptes,
XSS, factures payées modifiées…).

## Démarrage typique

1. L'administrateur se connecte et crée un hôtel (**Mes hôtels → Nouvel hôtel**) : informations, chambres et
   photos, puis tarifs et services. Les chambres sont générées automatiquement.
2. Dans **Utilisateurs**, il crée un ou plusieurs réceptionnistes et choisit **l'hôtel** de chacun.
3. Les clients s'inscrivent dans l'espace client, choisissent un hôtel et envoient une demande de réservation.
4. Les réceptionnistes de cet hôtel confirment ou refusent la demande, puis gèrent le séjour.

## Espace réceptionniste

Chaque hôtel a ses propres réceptionnistes (un ou plusieurs) ; un réceptionniste ne voit **que** son hôtel.
Sans hôtel assigné, il voit un message lui demandant de contacter l'administrateur.

| Page | Contenu |
|---|---|
| **Aujourd'hui** | Arrivées attendues et départs du jour avec check-in / check-out en un clic, clients présents, factures à encaisser |
| **Réservations réclamées** | Demandes des clients : *Confirmer* (factures émises, client prévenu) ou *Refuser* |
| **Toutes les réservations** | Filtre par statut, check-in, check-out, annulation, modification (chambre, dates, montant) |
| **Réservation au comptoir** | Client existant (CIN ou e-mail) ou nouveau client ; réservation confirmée + facture, check-in immédiat possible |
| **Calendrier des chambres** | Grille chambre × jour sur 14 jours ; cliquer une case libre pré-remplit une réservation |
| **Clients** | Recherche, fiche client avec historique des séjours dans l'hôtel, montant restant à payer, modification du profil |
| **Factures de paiement** | Encaissement avec le mode de paiement (espèces, carte, virement) ; facture imprimable regroupant toutes les chambres d'une demande |
| **Statut des chambres** | Disponible / occupée / maintenance |
| **Planifier un nettoyage** | Tâches de ménage des chambres de l'hôtel |

Règles :

- Une chambre ne peut pas être réservée deux fois sur des dates qui se chevauchent.
- Modifier une réservation met à jour sa facture si elle n'est pas encore payée ; une facture payée n'est plus modifiée.
- Pendant un séjour en cours, seule la date de départ peut changer.
- Annuler une réservation supprime sa facture impayée.
- Un client créé au comptoir définit son mot de passe avec **Mot de passe oublié**.
- Check-in seulement à partir de la date d'arrivée ; au check-out, une facture impayée est signalée.
- Une chambre occupée par un client ne peut pas être passée en « Disponible » ou « Maintenance ».
- Les factures payées ne sont plus modifiables ; seul l'administrateur peut supprimer une réservation.
- La réception modifie le nom et le téléphone d'un client, jamais son e-mail (qui sert à réinitialiser le mot de passe).

## Autres fonctions

- **Mot de passe oublié** en 3 étapes : CIN + e-mail, code à 6 chiffres (10 min, 5 essais), nouveau mot de passe.
  En développement, le code s'affiche dans la console du serveur.
- **Rappels de nettoyage** : envoyés à chaque visite de l'agent et toutes les 60 s dans le navigateur. Pour les
  envoyer sans page ouverte, planifier chaque minute `python manage.py send_cleaning_reminders`.
- **Comptes** : seuls les clients s'inscrivent seuls. Les employés (réceptionnistes, agents, chefs) sont créés par
  l'administrateur dans **Utilisateurs** (`ALLOW_STAFF_SIGNUP = False` dans `hotel/settings.py`). Un compte
  administrateur ne s'inscrit jamais publiquement : `createsuperuser`, ou un super-administrateur dans
  **Utilisateurs**. Un administrateur ordinaire ne peut pas modifier un autre administrateur.

## Personnalisation

Remplacez `static/videos/hero.mp4` et `static/videos/visite.mp4` par vos vidéos (mêmes noms),
`static/img/logo.svg` par votre logo, et le nom de l'hôtel dans `HOTEL_NAME` (`hotel/settings.py`).
Bootstrap 5 et Bootstrap Icons sont inclus en local.

## Structure

| Dossier | Contenu |
|---|---|
| `account/` | Utilisateurs, rôles, connexion, mot de passe oublié, tableaux de bord, notifications |
| `gestion_hotel/` | Hôtels (assistant 3 étapes), services, formules, réservation client, calcul des prix, événements |
| `gestion_rooms/` | Chambres, réservations, factures, ménage, espace réceptionniste (`reception_views.py`) |
| `gestion_repas/` | Menu du jour et stock de la cuisine |
| `gestion_equipments/` | Stock d'équipements (à venir) |
| `templates/`, `static/` | Gabarits HTML et ressources |
| `docs/jira_backlog.csv` | Backlog importable dans Jira (epics, user stories US01–US28, sprints, bugs) |
