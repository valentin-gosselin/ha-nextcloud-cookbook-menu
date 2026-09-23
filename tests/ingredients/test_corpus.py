"""Parser against the real corpus: 545 lines from 59 Nextcloud Cookbook recipes (export from 16/09/2026).

The expected values (`attendus_parseur.json`) were reviewed line by line. When the parser still
gets it wrong, the expected value holds the correct answer: these lines count as failures.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from custom_components.nextcloud_cookbook_menu.ingredients import analyser

FIXTURES = Path(__file__).parents[1] / "fixtures"
SEUIL = 0.95


def _resume(ligne: str) -> list[dict]:
    return [
        {
            k: v
            for k, v in {
                "nom": i.nom,
                "quantite": i.quantite,
                "quantite_max": i.quantite_max,
                "unite": i.unite,
                "cle": i.cle,
                "section": i.section or None,
                "facultatif": i.facultatif or None,
                "vague": i.vague,
            }.items()
            if v is not None
        }
        for i in analyser(ligne)
    ]


def test_precision_sur_le_corpus_reel() -> None:
    attendus = json.loads((FIXTURES / "attendus_parseur.json").read_text(encoding="utf-8"))
    rates = {ligne: (_resume(ligne), attendu) for ligne, attendu in attendus.items() if _resume(ligne) != attendu}
    precision = 1 - len(rates) / len(attendus)
    detail = "\n".join(f"{ligne!r}\n  obtenu : {o}\n  attendu : {a}" for ligne, (o, a) in rates.items())
    assert precision >= SEUIL, f"précision {precision:.1%} < {SEUIL:.0%}\n{detail}"
    # Known and accepted failures as of 16/09/2026: if one of them gets fixed, update this list.
    assert set(rates) == {"4 Tortillas", "225 g de macarons un peu rassis"}, detail


def test_toutes_les_lignes_du_corpus_sans_exception_et_rapide() -> None:
    corpus = json.loads((FIXTURES / "corpus_recettes.json").read_text(encoding="utf-8"))
    lignes = [ligne for recette in corpus for ligne in recette["ingredients"]]
    assert len(lignes) == 545
    debut = time.perf_counter()
    for ligne in lignes:
        for ingredient in analyser(ligne):
            assert ingredient.nom
            assert ingredient.cle is not None
    assert time.perf_counter() - debut < 0.5
