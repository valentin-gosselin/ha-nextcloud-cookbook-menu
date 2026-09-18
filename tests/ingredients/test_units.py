"""Lecture des unités."""

from __future__ import annotations

import pytest

from custom_components.nextcloud_cookbook_menu.ingredients.units import UNITES, Famille, famille, lire_unite


@pytest.mark.parametrize(
    ("texte", "code", "reste"),
    [
        ("g de farine", "g", "de farine"),
        ("gr. de beurre", "g", "de beurre"),
        ("gros oignons", None, "gros oignons"),
        ("lait", None, "lait"),
        ("l de lait", "l", "de lait"),
        ("litre d'eau", "l", "d'eau"),
        ("gousses d'ail", "gousse", "d'ail"),
        ("potimarron", None, "potimarron"),
        ("c. à s. d'huile", "c. à s.", "d'huile"),
        ("càs miel", "c. à s.", "miel"),
        ("cassonade", None, "cassonade"),
        ("cacahuètes", None, "cacahuètes"),
        ("bolognaise", None, "bolognaise"),
    ],
)
def test_lire_unite(texte, code, reste) -> None:
    assert lire_unite(texte) == (code, reste)


def test_familles() -> None:
    assert famille("kg") is Famille.MASSE
    assert famille("cl") is Famille.VOLUME
    assert famille("c. à c.") is Famille.CUILLERE
    assert famille("pincée") is Famille.CONTENANT
    assert famille(None) is None
    assert famille("inconnue") is None
    assert UNITES["kg"].facteur == 1000
    assert UNITES["cl"].facteur == 10
