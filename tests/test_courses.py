"""Liste de courses dans Home Assistant (story 2.2)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.cookbook_menu.api import CookbookConnectionError, Recipe

from .test_menu import ajouter, elements

COURSES = "todo.valentin_cloud_exemple_fr_liste_de_courses"


@pytest.fixture(autouse=True)
async def langue_francaise(hass: HomeAssistant) -> None:
    await hass.config.async_update(language="fr")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def courses(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    return {ligne["summary"]: ligne for ligne in await elements(hass, COURSES)}


async def cocher(hass: HomeAssistant, libelle: str, statut: str = "completed") -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "update_item", {"entity_id": COURSES, "item": libelle, "status": statut}, blocking=True
    )


async def test_courses_suivent_le_menu(hass: HomeAssistant, entree) -> None:
    assert await courses(hass) == {}
    await ajouter(hass, "salade cesar")
    lignes = await courses(hass)
    assert lignes["Citron (1)"]["description"] == "Salade César au poulet pour 2"
    assert hass.states.get(COURSES).state == str(len(lignes))

    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine", "item": "Salade César au poulet"},
        blocking=True,
    )
    assert await courses(hass) == {}


async def test_changer_les_couverts_recalcule(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "salade cesar")
    assert "Escalope de poulet (1)" in await courses(hass)
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine",
            "item": "Salade César au poulet",
            "description": "pour 8",
        },
        blocking=True,
    )
    assert "Escalope de poulet (4)" in await courses(hass)


async def test_cochage_conserve_si_quantite_stable_ou_en_baisse(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    await ajouter(hass, "salade cesar")  # ne touche pas aux tomates
    assert (await courses(hass))["Tomates (2)"]["status"] == "completed"

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine",
            "item": "Carry de poulet",
            "description": "pour 3",
        },
        blocking=True,
    )
    assert (await courses(hass))["Tomates (1)"]["status"] == "completed"


async def test_quantite_en_hausse_decoche_avec_mention(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    await ajouter(hass, "couscous", description="pour 2")
    ligne = (await courses(hass))["Tomates (3) +1"]
    assert ligne["status"] == "needs_action"

    await cocher(hass, "Tomates (3) +1")
    assert (await courses(hass))["Tomates (3)"]["status"] == "completed"


async def test_recette_modifiee_apres_cochage(hass: HomeAssistant, entree, mock_client, recettes) -> None:
    """Critère ajouté par le party mode du 16/09 : pas de réapparition silencieuse."""
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Oignons (2)")
    carry = recettes["2176038"]
    recettes["2176038"] = Recipe(
        **{
            **{f: getattr(carry, f) for f in carry.__slots__},
            "ingredients": ("300 g d'oignons", "6 gousses d'ail"),
        }
    )
    coordinateur = entree.runtime_data.coordinator
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    lignes = await courses(hass)
    assert lignes["Oignons (3) +1"]["status"] == "needs_action"
    assert "Tomates (2)" not in lignes

    recettes["2176038"] = Recipe(
        **{**{f: getattr(carry, f) for f in carry.__slots__}, "ingredients": ("100 g d'oignons",)}
    )
    await cocher(hass, "Oignons (3) +1")
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    assert (await courses(hass))["Oignons (1)"]["status"] == "completed"


async def test_lignes_manuelles_preservees(hass: HomeAssistant, entree) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES, "item": "Papier toilette"}, blocking=True
    )
    await ajouter(hass, "salade cesar")
    lignes = list(await courses(hass))
    assert lignes[-1] == "Papier toilette"

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": COURSES,
            "item": "Papier toilette",
            "rename": "Papier toilette x12",
            "description": "promo",
            "status": "completed",
        },
        blocking=True,
    )
    ligne = (await courses(hass))["Papier toilette x12"]
    assert (ligne["description"], ligne["status"]) == ("promo", "completed")

    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine", "item": "Salade César au poulet"},
        blocking=True,
    )
    assert list(await courses(hass)) == ["Papier toilette x12"]
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Papier toilette x12"}, blocking=True
    )
    assert await courses(hass) == {}


async def test_ligne_calculee_non_renommable(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "salade cesar")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            TODO_DOMAIN,
            "update_item",
            {"entity_id": COURSES, "item": "Citron (1)", "rename": "Citrons bio"},
            blocking=True,
        )
    planificateur = entree.runtime_data.planner
    with pytest.raises(ServiceValidationError):
        planificateur.async_modifier_course("inconnu", texte=None, description=None, fait=True)
    with pytest.raises(ServiceValidationError):
        planificateur.async_ajouter_course("  ")


async def test_supprimer_une_ligne_calculee_la_masque(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Thym (1 branche)"}, blocking=True
    )
    assert "Thym (1 branche)" not in await courses(hass)
    await ajouter(hass, "carry", description="pour 6")
    assert "Thym (2 branches) +1 branche" in await courses(hass)


async def test_panne_nextcloud_ne_perd_pas_les_cochages(hass: HomeAssistant, entree, mock_client) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    coordinateur = entree.runtime_data.coordinator
    mock_client.async_get_recipes.side_effect = CookbookConnectionError("coupure")
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    entree.runtime_data.planner.liste_de_courses()
    mock_client.async_get_recipes.side_effect = None
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    assert (await courses(hass))["Tomates (2)"]["status"] == "completed"


async def test_plat_termine_ne_compte_plus(hass: HomeAssistant, entree) -> None:
    entree.runtime_data.planner.async_ajouter_plat("salade cesar", fait=True)
    await hass.async_block_till_done()
    assert await courses(hass) == {}


async def test_meme_recette_deux_fois(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 2")
    await ajouter(hass, "carry", description="pour 4")
    assert (await courses(hass))["Ail (6 gousses)"]["description"] == "Carry de poulet pour 6"


async def test_semaine_suivante_repart_de_zero(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine", "item": "Carry de poulet"},
        blocking=True,
    )
    assert await courses(hass) == {}
    await ajouter(hass, "carry", description="pour 6")
    assert (await courses(hass))["Tomates (2)"]["status"] == "needs_action"
