"""Génère des étapes de cuisine écrites pour les tests, sans reprendre de texte de site."""

import json
import random
from pathlib import Path

FIXTURES = Path("tests/fixtures")
corpus = json.loads((FIXTURES / "corpus_recettes.json").read_text(encoding="utf-8"))

PREPARATION = [
    "Sortez les ingrédients, pesez-les et posez-les à portée de main.",
    "Épluchez et coupez les légumes en morceaux réguliers.",
    "Émincez finement l'oignon et l'ail, réservez-les dans un bol.",
    "Rincez les herbes, séchez-les et ciselez-les grossièrement.",
    "Préchauffez le four pendant que vous préparez le reste.",
    "Salez, poivrez, puis mélangez pour répartir l'assaisonnement.",
]
CUISSON = [
    "Faites chauffer un filet d'huile dans une grande poêle, puis faites revenir {duree}.",
    "Couvrez et laissez mijoter à feu doux {duree}, en remuant de temps en temps.",
    "Enfournez et laissez cuire {duree}, jusqu'à ce que le dessus soit doré.",
    "Portez à ébullition, baissez le feu et comptez {duree} de cuisson.",
    "Faites dorer sur chaque face {duree}, sans percer la viande.",
    "Ajoutez le liquide, mélangez et poursuivez la cuisson {duree}.",
    "Laissez réduire à découvert {duree}, le temps que la sauce nappe la cuillère.",
    "Faites cuire à la vapeur {duree}, la pointe du couteau doit entrer sans forcer.",
]
ATTENTE = [
    "Laissez reposer {duree} hors du feu avant de servir.",
    "Réservez au frais {duree}, le temps que les saveurs se mélangent.",
    "Laissez mariner {duree} en retournant une fois.",
    "Laissez la pâte lever {duree} à l'abri des courants d'air.",
    "Laissez refroidir {duree} avant de démouler.",
]
FINITION = [
    "Rectifiez l'assaisonnement et servez sans attendre.",
    "Dressez dans les assiettes et parsemez d'herbes fraîches.",
    "Mélangez délicatement pour ne pas écraser les morceaux.",
    "Servez bien chaud, avec le reste de la sauce à part.",
    "Goûtez, ajustez le sel et le poivre, puis passez à table.",
]
DUREES_COURTES = ["2 min", "3 min", "5 min", "2 ou 3 min", "1-2 minutes", "quelques instants", "30 secondes"]
DUREES_MOYENNES = ["10 min", "15 minutes", "20 mn", "25 mn", "40 à 45 minutes", "1/2 heure", "½ heure"]
DUREES_LONGUES = ["1 h", "1h", "1 h 30", "2 heures", "une heure", "12 heures", "3 h"]

recettes = []
for recette in corpus:
    alea = random.Random(int(recette["id"]))
    etapes = [alea.choice(PREPARATION)]
    for _ in range(alea.randint(1, 3)):
        etapes.append(alea.choice(CUISSON).format(duree=alea.choice(DUREES_COURTES + DUREES_MOYENNES)))
    if alea.random() < 0.6:
        etapes.append(alea.choice(ATTENTE).format(duree=alea.choice(DUREES_MOYENNES + DUREES_LONGUES)))
    etapes.append(alea.choice(FINITION))
    recettes.append(
        {
            "id": recette["id"],
            "name": recette["name"],
            "description": "Recette d'exemple écrite pour les tests.",
            "prepTime": alea.choice([None, "PT15M", "PT30M"]),
            "cookTime": alea.choice([None, "PT20M", "PT45M"]),
            "totalTime": alea.choice([None, "PT1H", "PT1H30M"]),
            "tool": [],
            "recipeInstructions": etapes,
        }
    )
(FIXTURES / "instructions_recettes.json").write_text(
    json.dumps(recettes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
)
print(len(recettes), "recettes,", sum(len(r["recipeInstructions"]) for r in recettes), "étapes")
