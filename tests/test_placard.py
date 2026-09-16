"""Placard (story 2.3)."""

from __future__ import annotations

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant

from custom_components.cookbook_menu.ingredients.pantry import cles_placard, est_au_placard, texte_rappel

from .test_courses import COURSES, cocher, courses
from .test_menu import ajouter

RAPPEL = "À vérifier au placard"


@pytest.fixture(autouse=True)
async def langue_francaise(hass: HomeAssistant) -> None:
    await hass.config.async_update(language="fr")


async def installer(hass: HomeAssistant, config_entry, **options) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, **options})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def rappel(lignes: dict) -> str:
    return next(libelle for libelle in lignes if libelle.startswith(RAPPEL))


def test_familles_et_cles() -> None:
    placard = cles_placard(["Huile", "Sel", "Sucre", ""])
    assert est_au_placard("huile sesame", placard)
    assert est_au_placard("sel", placard)
    assert not est_au_placard("sucre glace", placard)
    assert not est_au_placard("vinaigre balsamique", placard)
    assert est_au_placard("vinaigre balsamique", cles_placard(["Vinaigre"]))


def test_texte_rappel_limite_a_cinq() -> None:
    noms = ["Sel", "Poivre", "Huile", "Cumin", "Curry", "Paprika", "Muscade"]
    assert texte_rappel(noms, "À vérifier : {produits}", " et {n} autres") == (
        "À vérifier : sel, poivre, huile, cumin, curry et 2 autres"
    )
    assert texte_rappel(noms[:2], "À vérifier : {produits}", " et {n} autres") == "À vérifier : sel, poivre"


async def test_couscous_sans_placard(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Critère de la story : ni huile d'olive, ni épices à couscous, ni harissa si elle est au placard."""
    await installer(hass, config_entry, pantry=["Huile d'olive", "Épices à couscous", "Harissa", "Sel"])
    await ajouter(hass, "couscous")
    lignes = await courses(hass)
    assert not any(libelle.startswith(("Huile", "Épices", "Harissa")) for libelle in lignes)
    assert rappel(lignes) == "À vérifier au placard : épices à couscous, harissa, huile d'olive"
    assert next(iter(lignes)).startswith(RAPPEL)


async def test_placard_par_defaut_et_rappel_desactivable(
    hass: HomeAssistant, mock_client, config_entry
) -> None:
    await installer(hass, config_entry, pantry_reminder=False)
    await ajouter(hass, "salade cesar")
    lignes = await courses(hass)
    assert not any(libelle.startswith(("Sel", "Poivre", "Vinaigre", RAPPEL)) for libelle in lignes)


async def test_il_n_y_a_plus_d_huile(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await ajouter(hass, "carry", description="pour 6")
    assert "Huile (4 c. à s.)" not in await courses(hass)

    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES, "item": "huile"}, blocking=True
    )
    lignes = await courses(hass)
    assert lignes["Huile (4 c. à s.)"]["description"] == "Carry de poulet pour 6, au placard, signalé épuisé"

    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES, "item": "Huile d'olive"}, blocking=True
    )
    assert "Huile d'olive" in await courses(hass)  # épuisé mais inutilisé par le menu : ligne sans quantité

    await cocher(hass, "Huile d'olive")
    await cocher(hass, "Huile (4 c. à s.)")
    lignes = await courses(hass)
    assert "Huile d'olive" not in lignes
    assert "Huile (4 c. à s.)" not in lignes  # rachetée : retour au placard
    assert "huile" in rappel(lignes)


async def test_rappel_coche_puis_nouveau_produit(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await ajouter(hass, "salade cesar")
    libelle = rappel(await courses(hass))
    await cocher(hass, libelle)
    assert (await courses(hass))[libelle]["status"] == "completed"

    await ajouter(hass, "carry")  # ajoute huile au placard utilisé
    nouveau = rappel(await courses(hass))
    assert nouveau != libelle
    assert (await courses(hass))[nouveau]["status"] == "needs_action"

    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": nouveau}, blocking=True
    )
    assert not any(libelle.startswith(RAPPEL) for libelle in await courses(hass))


async def test_supprimer_un_produit_epuise(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES, "item": "Sel"}, blocking=True
    )
    assert "Sel" in await courses(hass)
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Sel"}, blocking=True
    )
    assert "Sel" not in await courses(hass)
    assert config_entry.runtime_data.planner.stockage.donnees.placard_epuise == {}
