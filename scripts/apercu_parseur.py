"""Affiche l'analyse de chaque ligne distincte du corpus (outil de relecture du parseur).

Usage : python scripts/apercu_parseur.py [--json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.cookbook_menu.ingredients.parser import analyser

CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "corpus_recettes.json"


def _nombre(valeur: float | None) -> str:
    if valeur is None:
        return "-"
    return str(int(valeur)) if valeur == int(valeur) else str(valeur)


def lignes_distinctes() -> list[str]:
    vues: dict[str, None] = {}
    for recette in json.loads(CORPUS.read_text(encoding="utf-8")):
        for ligne in recette["ingredients"]:
            vues.setdefault(ligne, None)
    return list(vues)


def decrire(ligne: str) -> str:
    morceaux = []
    for i in analyser(ligne):
        if i.section:
            morceaux.append(f"§ {i.nom}")
            continue
        texte = _nombre(i.quantite)
        if i.quantite_max is not None:
            texte += f"~{_nombre(i.quantite_max)}"
        texte += f" [{i.unite or ''}] {i.nom} <{i.cle}>"
        if i.note:
            texte += f" {{{i.note}}}"
        if i.facultatif:
            texte += " ?"
        if i.vague:
            texte += f" vague={i.vague}"
        morceaux.append(texte)
    return " || ".join(morceaux)


if __name__ == "__main__":
    for ligne in lignes_distinctes():
        print(f"{ligne!r} => {decrire(ligne)}")
