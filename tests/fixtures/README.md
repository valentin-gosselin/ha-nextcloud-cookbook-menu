# Jeux d'essai

- `corpus_recettes.json` : listes d'ingrédients de 59 recettes réelles (59 recettes, 545 lignes), avec
  la catégorie, le rendement et le lien vers la page d'origine. Ce sont ces lignes, courtes et
  factuelles, qui servent à durcir l'analyse des ingrédients.
- `attendus_parseur.json` : résultat attendu de l'analyse pour chacune de ces lignes.
- `instructions_recettes.json` : étapes de cuisine **écrites pour les tests**, avec la même variété de
  durées que des recettes réelles (140 minuteurs, 19 formats). Aucun texte n'est repris d'un site de
  cuisine. Régénérer avec `python scripts/generer_etapes_de_test.py`.
- `phrases_vocales.json` : variantes de commandes vocales et résultat attendu, en français et en anglais.
