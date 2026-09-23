"""Parser rules, one by one."""

from __future__ import annotations

import pytest

from custom_components.nextcloud_cookbook_menu.ingredients import analyser


def un(ligne: str):
    resultat = analyser(ligne)
    assert len(resultat) == 1, resultat
    return resultat[0]


@pytest.mark.parametrize(
    ("ligne", "quantite", "quantite_max"),
    [
        ("2 oeufs", 2, None),
        ("0,5 Citron(s)", 0.5, None),
        ("1.250 kg de poulet", 1.25, None),
        ("1/2 c. à café de safran", 0.5, None),
        ("½ concombre", 0.5, None),
        ("1 ½ tasse de lait", 1.5, None),
        ("1 1/2 verre d'eau", 1.5, None),
        ("7-8 champignons", 7, 8),
        ("2 à 3 cuillères à soupe de pâte de curry", 2, 3),
        ("une gousse d'ail", 1, None),
        ("deux carottes", 2, None),
        ("1 verre 1/2 de vin blanc sec", 1.5, None),
        ("1/0 citron", 0, None),
    ],
)
def test_quantites(ligne, quantite, quantite_max) -> None:
    ingredient = un(ligne)
    assert ingredient.quantite == quantite
    assert ingredient.quantite_max == quantite_max


@pytest.mark.parametrize(
    ("ligne", "unite", "nom"),
    [
        ("180g de farine", "g", "Farine"),
        ("250gr de mascarpone", "g", "Mascarpone"),
        ("2 kilos de pommes", "kg", "Pommes"),
        ("50cL de lait froid", "cl", "Lait froid"),
        ("1,5 L d'eau", "l", "Eau"),
        ("1/4 de litre de lait", "l", "Lait"),
        ("2 c. à soupe d'huile", "c. à s.", "Huile"),
        ("2 CàS de moutarde", "c. à s.", "Moutarde"),
        ("2 cs de beurre de cacahuète", "c. à s.", "Beurre de cacahuète"),
        ("4 cuil. à soupe bombées de sucre", "c. à s.", "Sucre"),
        ("1 cuillères à café rases de cannelle", "c. à c.", "Cannelle"),
        ("½ c à c piment", "c. à c.", "Piment"),
        ("3 cc de curry", "c. à c.", "Curry"),
        ("1 càc Moutarde", "c. à c.", "Moutarde"),
        ("1 tbsp olive oil", "c. à s.", "Olive oil"),
        ("1 cuil. de café soluble", "cuillère", "Café soluble"),
        ("1/4 gou. Ail", "gousse", "Ail"),
        ("1 sac. Levure chimique", "sachet", "Levure chimique"),
        ("1 grosses poignées de coriandre", "poignée", "Coriandre"),
        ("4 tranches épaisses de jambon à l'os", "tranche", "Jambon à l'os"),
        ("1.5 cL baby de jus de citron", "cl", "Jus de citron"),
        ("1 feuille ou pincée de quatre-épices", "feuille", "Quatre-épices"),
        ("paquet de crêpe dentelle", "paquet", "Crêpe dentelle"),
        ("gousse ail", None, "Gousse ail"),
        ("2 gros oignons", None, "Gros oignons"),
        ("1 potimarron", None, "Potimarron"),
        ("2 lardons", None, "Lardons"),
        ("1 bouquet garni", None, "Bouquet garni"),
        ("5 grains de poivre gris", "grain", "Poivre gris"),
    ],
)
def test_unites_et_noms(ligne, unite, nom) -> None:
    ingredient = un(ligne)
    assert ingredient.unite == unite
    assert ingredient.nom == nom


@pytest.mark.parametrize(
    ("ligne", "attendus"),
    [
        ("Sel, poivre", ["Sel", "Poivre"]),
        ("Sel et poivre", ["Sel", "Poivre"]),
        ("Sel poivre", ["Sel", "Poivre"]),
        ("poivre et sel", ["Poivre", "Sel"]),
        ("Huile d'olive, sel, poivre", ["Huile d'olive", "Sel", "Poivre"]),
        ("1/2 verre d'eau, 1/2 verre de sucre", ["Eau", "Sucre"]),
        ("1 pincée de muscade et poivre", ["Muscade", "Poivre"]),
        ("Pommes, poires et scoubidous", ["Pommes", "Poires", "Scoubidous"]),
        ("Épices (cumin, paprika)", ["Épices"]),
        ("Un plat de pâtes, avec beaucoup de fromage râpé dessus", ["Plat de pâtes"]),
    ],
)
def test_lignes_multiples(ligne, attendus) -> None:
    assert [i.nom for i in analyser(ligne)] == attendus


def test_muscade_et_poivre_gardent_la_quantite() -> None:
    muscade, poivre = analyser("1 pincée de muscade et poivre")
    assert (muscade.quantite, muscade.unite) == (1, "pincée")
    assert (poivre.quantite, poivre.unite) == (1, "pincée")


@pytest.mark.parametrize(
    "ligne",
    ["Meringue :", "Gâteau de Savoie :", "Pour la sauce", "Pour la pain :", "Pour les boulettes de viande"],
)
def test_sections(ligne) -> None:
    ingredient = un(ligne)
    assert ingredient.section
    assert not ingredient.nom.endswith(":")


@pytest.mark.parametrize("ligne", ["Pour 4 personnes :", "Poulet pour la cuisson au four ce soir avec amis"])
def test_pas_des_sections(ligne) -> None:
    assert not un(ligne).section


@pytest.mark.parametrize(
    ("ligne", "nom", "note", "facultatif"),
    [
        ("8 pilons de poulet (fermier de préférence)", "Pilons de poulet", "fermier de préférence", False),
        ("Coriandre fraîche (facultatif)", "Coriandre fraîche", "facultatif", True),
        ("1 haché piment thaï (facultatif)", "Piment thaï", "facultatif", True),
        ("450g Boeuf haché, maigre", "Boeuf haché", "maigre", False),
        (
            "75 g de beurre + une noisette pour beurrer le plat",
            "Beurre",
            "+ une noisette pour beurrer le plat",
            False,
        ),
        ("2 paquets de croûtons à l'ail de 90gr, soit 180gr", "Croûtons à l'ail", "90gr; soit 180gr", False),
        ("1 barquette de 250gr de tomates cerise mûres", "Tomates cerise mûres", "250gr", False),
        (
            "1 boîte de 500gr net égoutté de cocktail de fruits",
            "Cocktail de fruits",
            "500gr net égoutté",
            False,
        ),
        ("sucre glace ou gelée de groseilles", "Sucre glace", "ou gelée de groseilles", False),
        ("2 feuilles de quatre-épices ou 1 pincée", "Quatre-épices", "ou 1 pincée", False),
        ("1 verre (shooter) d'alcool de type Amaretto", "Alcool de type Amaretto", "shooter", False),
        ("Légumes supplémentaires si désiré", "Légumes supplémentaires", "si désiré", True),
        ("1 feuille de laurier pour le riz", "Laurier", "pour le riz", False),
        ("2 cuillères à soupe de farine rases", "Farine", None, False),
        ("10 ml, haché d’ ail", "Ail", None, False),
        ("250gr de farine ( pâte )", "Farine", "pâte", False),
        ("1 oignon (rouge", "Oignon", "rouge", False),
    ],
)
def test_notes(ligne, nom, note, facultatif) -> None:
    ingredient = un(ligne)
    assert ingredient.nom == nom
    assert ingredient.note == note
    assert ingredient.facultatif is facultatif


@pytest.mark.parametrize(
    ("ligne", "vague", "nom"),
    [("un peu de lait", "un peu", "Lait"), ("quelques pistils de safran", "quelques", "Pistils de safran")],
)
def test_quantites_vagues(ligne, vague, nom) -> None:
    ingredient = un(ligne)
    assert ingredient.vague == vague
    assert ingredient.quantite is None
    assert ingredient.nom == nom


@pytest.mark.parametrize("ligne", ["", "   ", "-", None, 42])
def test_lignes_vides_ou_invalides(ligne) -> None:
    assert analyser(ligne) == []


@pytest.mark.parametrize("ligne", ["(((", "de", "1 de", "12 g", "½", "1/2 c. à s.", "?!", "d'", "1 kg de"])
def test_lignes_bizarres_gardent_le_texte(ligne) -> None:
    for ingredient in analyser(ligne):
        assert ingredient.nom
        assert ingredient.brut == ligne


def test_espaces_et_apostrophes_normalises() -> None:
    ingredient = un("  200 g   d’oignons ")
    assert ingredient.nom == "Oignons"
    assert ingredient.brut == "  200 g   d’oignons "
