# Changelog

Toutes les évolutions notables de ce projet sont consignées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnage [SemVer](https://semver.org/lang/fr/).

## [Unreleased]

### Modifié
- Home Assistant 2026.9.0 minimum.

### Ajouté
- Historique des plats : action `get_history`, question vocale « Quand est-ce qu'on a mangé du carry ? », durée de conservation réglable. `new_week` garde les plats à venir.
- Outils pour les agents LLM (API Assist) : chercher une recette, ajouter au menu, retirer, lire le menu, consulter l'historique.
- Voix avec l'agent Assist par défaut, en français et en anglais : ajouter un plat au menu (jour et couverts compris), demander ce qu'on mange, retirer un plat.
- Synchronisation facultative du menu et de la liste de courses vers des listes todo existantes (celle ouverte au magasin), sans jamais toucher aux lignes ajoutées ailleurs. Les cochages faits dans la liste cible sont remontés.
- Actions `add_to_menu`, `remove_from_menu`, `set_servings`, `new_week` et `search_recipes`, avec réponses exploitables par les scripts. Les jours s'écrivent en toutes lettres (« jeudi », « demain »).
- Placard : produits de base jamais ajoutés aux courses (liste réglable), avec une ligne de rappel à vérifier avant de partir. Un produit du placard ajouté à la main est signalé épuisé et revient au placard une fois coché.
- Liste « Liste de courses » calculée depuis le menu : quantités mises à l'échelle des couverts, produits fusionnés entre recettes, arrondis à l'achat, rangés par rayon. Les lignes cochées ou ajoutées à la main ne sont jamais écrasées.
- Liste « Menu de la semaine » : un plat par ligne, lié automatiquement à la recette la plus proche (tolérant aux accents et aux fautes), jour en échéance, couverts réglables dans la description.
- Configuration par l'UI (URL, utilisateur, mot de passe d'application), avec test de connexion, réauthentification et reconfiguration.
- Options du foyer : couverts par défaut, catégories exclues, intervalle de rafraîchissement.
- Analyse des lignes d'ingrédients en français (quantités, fractions, plages, unités, sections, notes, lignes multiples) et clé de fusion des produits. Validée sur un corpus réel de 545 lignes.
- Lecture des recettes Nextcloud Cookbook avec cache (détail rechargé seulement si la recette a changé) et diagnostics sans secret.
- Squelette de l'intégration `cookbook_menu`, CI (hassfest, HACS, ruff, pytest), release HACS et script de déploiement vers le HA de dev.
