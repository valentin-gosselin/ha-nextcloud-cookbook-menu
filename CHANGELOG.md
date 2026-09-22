# Changelog

Toutes les évolutions notables de ce projet sont consignées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnage [SemVer](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- Minuteurs côté Home Assistant : un minuteur lancé depuis une recette démarre aussi un minuteur Assist sur l'appareil vocal choisi dans les options (il sonne dessus), démarre l'entité `timer` choisie, et émet l'événement `nextcloud_cookbook_menu_timer_started` pour les automatisations. Nouvelle action `start_timer`. Sans rien régler, le compte à rebours de la carte fonctionne comme avant.
- Carte Réserve : bouton « Retirer du stock » sur chaque produit, pour jeter un produit périmé ou corriger une erreur.
- Produits récurrents : ce qui part hors menu (beurre des tartines, lait, café) revient dans la liste à sa fréquence, une semaine par défaut, réglable par produit dans la carte Réserve.

### Modifié
- Achats au conditionnement réel : une recette qui demande 10 g de beurre fait acheter une plaquette de 250 g, 9 œufs deviennent une boîte de 12. Le reste sert aux plats suivants au lieu de racheter chaque semaine.
- Durées de conservation par produit : ail, oignon et pommes de terre 30 jours, œufs 21, tomates et salade 5, viande hachée 2, au lieu de 7 jours pour tout le frais. Un produit inconnu compte désormais 7 jours et non 60.
- Morceaux de boucherie et poissons reconnus (bavette, entrecôte, magret, dorade...) : ils étaient classés en épicerie, donc gardés 60 jours.
- Les sections de la carte Réserve disent ce qu'elles font : « Toujours là » (présent ou manquant) et « Acheté pour le menu » (quantités et péremption).
- Les minuteurs s'appellent « Étape 3 - Salade César » au lieu du seul nom de la recette.
- Un produit qui se garde (index du placard : levure, miel, pâtes, conserves...) coché dans les courses rejoint le **placard** et non le frigo. Les produits déjà au frigo qui sont dans l'index y sont déplacés à la mise à jour.

## [1.1.0] - 2026-09-19

### Ajouté
- Carte `custom:cookbook-recipes-card` : consultation des recettes en grille de vignettes, recherche et filtre par catégorie, sans passer par le menu. La fiche ouverte depuis cette carte propose le jour, les couverts et l'ajout au menu.
- Les photos sont servies en vignette (`.../image/<entrée>/<recette>/thumb`), pas en pleine taille, pour la grille.

### Corrigé
- La tâche de minuit (consommation, expiration) s'exécutait hors de la boucle Home Assistant, ce qui est interdit pour du code qui touche à l'état.
- La ressource Lovelace laissée par le domaine `cookbook_menu` (avant la 1.0.0) est retirée automatiquement.

## [1.0.0] - 2026-09-18

Première version publique.

### Modifié
- Le domaine devient `nextcloud_cookbook_menu` et l'intégration s'appelle « Nextcloud Cookbook Menu ». Le menu et la réserve d'une installation `cookbook_menu` sont repris automatiquement, mais l'entrée doit être supprimée puis recréée.
- La ligne « À vérifier au placard » et son option sont supprimées au profit de la réserve. Les lignes ajoutées à la main deviennent des produits « maison ».
- Home Assistant 2026.9.0 minimum.

### Corrigé
- Voix : une phrase française dite à un Home Assistant réglé en anglais était analysée avec les règles anglaises (« Ajoute une salade César au menu jeudi pour quatre » devenait un plat libre sans recette, sans jour ni couverts). La langue de la phrase prime désormais sur celle du pipeline. Au passage, l'anglais ne dit plus « on tomorrow ».

### Ajouté
- Voix : beaucoup plus de tournures comprises sans LLM (ajouter au menu, demander le menu, retirer, historique, « il n'y a plus de »), en français et en anglais. 132 phrases réelles sont rejouées à chaque test, contre-exemples compris (« ajoute du beurre à ma liste de courses » ne crée pas de plat).
- Carte réserve : le champ « Ajouter au placard » ouvre la liste des produits de l'index pas encore au placard, filtrée pendant la frappe, avec sélection multiple. La saisie libre reste possible.
- Index d'environ 300 produits de placard (épices, herbes sèches, condiments, pâtes, riz, farines, conserves...) : un produit ajouté à la main qui en fait partie rejoint le placard et non la maison. Carte réserve : ajout au placard, « Au placard » pour un produit de la maison, sortie du placard. Minuteurs visibles dans la fiche recette.
- Réserve : placard (présent ou manquant), frigo (cocher une ligne de courses, c'est acheter ; les plats cuisinés ou passés consomment ; restes réutilisés ; expiration 7 jours pour le frais, 60 pour l'épicerie) et maison (achats hors menu). Carte `custom:cookbook-stock-card`, phrase « il n'y a plus de... », action `out_of_stock`, outils LLM.
- Unités d'achat : l'ail en gousses ou en têtes, les herbes en bouquets, les légumes à la pièce, le beurre au poids, les sachets et boîtes. Blancs et jaunes rejoignent les œufs, le jus de citron les citrons. L'eau et le laurier sont au placard par défaut.
- Fiche recette dans la carte : photo, temps, ingrédients à l'échelle des couverts, étapes cochables, minuteurs lancés depuis les durées des étapes, écran maintenu allumé.
- Carte de tableau de bord `custom:cookbook-menu-card`, installée automatiquement : recherche de recette pendant la frappe, jour, couverts, ajout, et menu affiché avec « cuisiné » et suppression.
- Entités « Recette à ajouter » (toutes les recettes par leur nom), « Jour », « Couverts » et bouton « Ajouter au menu ».
- Connexion « Se connecter avec Nextcloud » (Login Flow v2) : plus besoin de créer et recopier un mot de passe d'application. La saisie manuelle reste possible.
- Documentation complète (README), auto-évaluation `quality_scale.yaml`, icône et logo.
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
- Squelette de l'intégration `nextcloud_cookbook_menu`, CI (hassfest, HACS, ruff, pytest), release HACS et script de déploiement vers le HA de dev.
