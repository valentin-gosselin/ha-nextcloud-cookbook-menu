# Changelog

Toutes les évolutions notables de ce projet sont consignées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnage [SemVer](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- Configuration par l'UI (URL, utilisateur, mot de passe d'application), avec test de connexion, réauthentification et reconfiguration.
- Options du foyer : couverts par défaut, catégories exclues, intervalle de rafraîchissement.
- Lecture des recettes Nextcloud Cookbook avec cache (détail rechargé seulement si la recette a changé) et diagnostics sans secret.
- Squelette de l'intégration `cookbook_menu`, CI (hassfest, HACS, ruff, pytest), release HACS et script de déploiement vers le HA de dev.
