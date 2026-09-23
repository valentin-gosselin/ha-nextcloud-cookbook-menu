"""LLM tools (story 3.2)."""

from __future__ import annotations

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.nextcloud_cookbook_menu.llm import async_get_tools

from .test_courses import courses


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")
    assert await async_setup_component(hass, "llm", {})


def contexte_llm() -> llm.LLMContext:
    return llm.LLMContext(platform="test", context=Context(), language="fr", assistant="conversation", device_id=None)


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def appeler(hass: HomeAssistant, outil: str, **arguments: Any) -> dict[str, Any]:
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, contexte_llm())
    return await api.async_call_tool(llm.ToolInput(tool_name=f"nextcloud_cookbook_menu__{outil}", tool_args=arguments))


async def test_outils_exposes_avec_consigne(hass: HomeAssistant, entree) -> None:
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, contexte_llm())
    noms = {outil.name for outil in api.tools}
    assert {
        "nextcloud_cookbook_menu__search_recipes",
        "nextcloud_cookbook_menu__add_to_menu",
        "nextcloud_cookbook_menu__remove_from_menu",
        "nextcloud_cookbook_menu__get_menu",
        "nextcloud_cookbook_menu__get_history",
    } <= noms
    assert "Nextcloud Cookbook Menu manages the household weekly menu" in api.api_prompt


async def test_pas_d_outils_sans_configuration_ou_autre_api(hass: HomeAssistant) -> None:
    assert async_get_tools(hass, contexte_llm(), llm.LLM_API_ASSIST) is None


async def test_chercher_puis_ajouter_par_identifiant(hass: HomeAssistant, entree) -> None:
    trouve = await appeler(hass, "search_recipes", query="salade cesar", limit=2)
    assert trouve["success"]
    vegetarienne = next(r for r in trouve["recipes"] if "végétarienne" in r["name"])

    ajout = await appeler(
        hass, "add_to_menu", dish="salade césar", recipe_id=vegetarienne["recipe_id"], day="jeudi", servings=3
    )
    assert ajout["success"]
    assert ajout["dish"] == "Salade César végétarienne (façon Rachel)"
    assert ajout["day"] == "2026-09-17"
    assert ajout["servings"] == 3
    assert await courses(hass)


async def test_ajouter_par_nom_et_lire_le_menu(hass: HomeAssistant, entree) -> None:
    ajout = await appeler(hass, "add_to_menu", dish="carry", day="tomorrow")
    assert ajout["dish"] == "Carry de poulet"
    menu = await appeler(hass, "get_menu")
    assert menu["today"] == "2026-09-16"
    assert menu["menu"] == [
        {
            "dish": "Carry de poulet",
            "recipe_id": "2176038",
            "day": "2026-09-17",
            "servings": 2,
            "cooked": False,
        }
    ]
    retrait = await appeler(hass, "remove_from_menu", dish="le carry")
    assert retrait["removed"]["dish"] == "Carry de poulet"
    assert (await appeler(hass, "get_menu"))["menu"] == []


async def test_historique(hass: HomeAssistant, entree) -> None:
    planificateur = entree.runtime_data.planner
    planificateur.stockage.donnees.historique.extend(
        [
            {"day": "2026-07-01", "summary": "Carry de poulet", "recipe_id": "2176038", "servings": 2},
            {"day": "2026-09-01", "summary": "Tartiflette", "recipe_id": "2178937", "servings": 4},
            {"day": "2026-08-15", "summary": "Carry de poulet", "recipe_id": "2176038", "servings": 2},
        ]
    )
    tout = await appeler(hass, "get_history")
    assert [p["day"] for p in tout["history"]] == ["2026-09-01", "2026-08-15", "2026-07-01"]
    carry = await appeler(hass, "get_history", dish="carry", limit=1)
    assert carry["history"] == [
        {"day": "2026-08-15", "summary": "Carry de poulet", "recipe_id": "2176038", "servings": 2}
    ]


@pytest.mark.parametrize(
    ("outil", "arguments", "erreur"),
    [
        ("add_to_menu", {"dish": "carry", "day": "un de ces quatre"}, "Invalid arguments"),
        ("add_to_menu", {"dish": "carry", "servings": 0}, "Invalid arguments"),
        ("add_to_menu", {"dish": "carry", "recipe_id": "000"}, ""),
        ("remove_from_menu", {"dish": "fondue"}, ""),
    ],
)
async def test_erreurs_rendues_lisibles(hass: HomeAssistant, entree, outil, arguments, erreur) -> None:
    resultat = await appeler(hass, outil, **arguments)
    assert resultat["success"] is False
    assert resultat["error"].startswith(erreur)


async def test_non_configure_au_moment_de_l_appel(hass: HomeAssistant, entree) -> None:
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, contexte_llm())
    outil = next(o for o in api.tools if o.name == "nextcloud_cookbook_menu__get_menu")
    await hass.config_entries.async_unload(entree.entry_id)
    resultat = await api.async_call_tool(llm.ToolInput(tool_name=outil.name, tool_args={}))
    assert resultat == {"success": False, "error": "Nextcloud Cookbook Menu is not set up"}
