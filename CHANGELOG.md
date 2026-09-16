# Changelog

Toutes les évolutions notables de ce projet sont consignées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnage [SemVer](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- Liste « Liste de courses » calculée depuis le menu : quantités mises à l'échelle des couverts, produits fusionnés entre recettes, arrondis à l'achat, rangés par rayon. Les lignes cochées ou ajoutées à la main ne sont jamais écrasées.
- Liste « Menu de la semaine » : un plat par ligne, lié automatiquement à la recette la plus proche (tolérant aux accents et aux fautes), jour en échéance, couverts réglables dans la description.
- Configuration par l'UI (URL, utilisateur, mot de passe d'application), avec test de connexion, réauthentification et reconfiguration.
- Options du foyer : couverts par défaut, catégories exclues, intervalle de rafraîchissement.
- Analyse des lignes d'ingrédients en français (quantités, fractions, plages, unités, sections, notes, lignes multiples) et clé de fusion des produits. Validée sur un corpus réel de 545 lignes.
- Lecture des recettes Nextcloud Cookbook avec cache (détail rechargé seulement si la recette a changé) et diagnostics sans secret.
- Squelette de l'intégration `cookbook_menu`, CI (hassfest, HACS, ruff, pytest), release HACS et script de déploiement vers le HA de dev.
