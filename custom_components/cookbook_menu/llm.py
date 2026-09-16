"""Outils pour les agents de conversation LLM (story 3.2).

HA exige que les outils d'une intégration soient préfixés par son domaine (depuis 2026.9) :
ils se nomment « cookbook_menu__<outil> ».
Chaque outil appelle le planificateur, comme les actions et la voix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

import voluptuous as vol
from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext, Tool, ToolInput
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
from .jours import lire_jour

if TYPE_CHECKING:
    from .planner import Planificateur

CONSIGNE = (
    "Cookbook Menu manages the household weekly menu from the Nextcloud Cookbook recipes. "
    "The shopping list is computed automatically from the menu: "
    "never add a recipe's ingredients to it yourself. "
    "Pantry staples (salt, oil, spices...) are left out on purpose; when the user says one is out of stock, "
    "add it to the Cookbook Menu shopping list. "
    "When the dish the user names could match several recipes, call cookbook_menu__search_recipes first and "
    "ask which one they mean before adding it."
)


def _planificateur(hass: HomeAssistant) -> Planificateur | None:
    for entree in hass.config_entries.async_loaded_entries(DOMAIN):
        return entree.runtime_data.planner
    return None


def _plat(plat: Any) -> dict[str, Any]:
    return {
        "dish": plat.summary,
        "recipe_id": plat.recipe_id,
        "day": plat.day.isoformat() if plat.day else None,
        "servings": plat.servings,
        "cooked": plat.done,
    }


class OutilCookbook(Tool):
    """Base : récupère le planificateur et convertit les erreurs en réponse lisible."""

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        raise NotImplementedError  # pragma: no cover

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        planificateur = _planificateur(hass)
        if planificateur is None:
            return {"success": False, "error": "Cookbook Menu is not set up"}
        try:
            arguments = self.parameters(tool_input.tool_args)
            return {"success": True, **await self._executer(planificateur, arguments)}
        except (vol.Invalid, ValueError) as err:
            return {"success": False, "error": f"Invalid arguments: {err}"}
        except HomeAssistantError as err:
            return {"success": False, "error": str(err) or type(err).__name__}


class ChercherRecettes(OutilCookbook):
    name = f"{DOMAIN}__search_recipes"
    description = (
        "Search the household recipes by name. Returns the best matches with a similarity score (0 to 1)."
    )
    parameters = vol.Schema(
        {
            vol.Required("query", description="Words from the dish name"): str,
            vol.Optional("limit", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        }
    )

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        return {
            "recipes": [
                {
                    "recipe_id": c.recette.id,
                    "name": c.recette.name,
                    "category": c.recette.category,
                    "score": c.score,
                }
                for c in planificateur.chercher_recettes(arguments["query"], arguments["limit"])
            ]
        }


class AjouterAuMenu(OutilCookbook):
    name = f"{DOMAIN}__add_to_menu"
    description = (
        "Add a dish to the weekly menu. Its ingredients are added to the shopping list automatically. "
        "Pass recipe_id when you know the exact recipe; otherwise the closest recipe name is used."
    )
    parameters = vol.Schema(
        {
            vol.Required("dish", description="Dish or recipe name"): str,
            vol.Optional("recipe_id", description="Exact recipe id from search_recipes"): str,
            vol.Optional("day", description="ISO date, weekday name, today or tomorrow"): str,
            vol.Optional("servings", description="Number of people"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=50)
            ),
        }
    )

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        jour = lire_jour(arguments.get("day"), dt_util.now().date())
        if "recipe_id" in arguments:
            return planificateur.async_ajouter_au_menu(
                arguments["dish"],
                jour=jour,
                couverts=arguments.get("servings"),
                recipe_id=arguments["recipe_id"],
            )
        return planificateur.async_ajouter_au_menu(
            arguments["dish"], jour=jour, couverts=arguments.get("servings")
        )


class RetirerDuMenu(OutilCookbook):
    name = f"{DOMAIN}__remove_from_menu"
    description = "Remove a dish from the weekly menu (its ingredients leave the shopping list)."
    parameters = vol.Schema({vol.Required("dish", description="Name of the dish in the menu"): str})

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        plat = planificateur.plat_par_nom(arguments["dish"])
        planificateur.async_supprimer_plats([plat.uid])
        return {"removed": _plat(plat)}


class LireMenu(OutilCookbook):
    name = f"{DOMAIN}__get_menu"
    description = "Get the weekly menu: dishes with their planned day, servings and whether they were cooked."
    parameters = vol.Schema({})

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        return {"today": dt_util.now().date().isoformat(), "menu": [_plat(p) for p in planificateur.menu]}


class LireHistorique(OutilCookbook):
    name = f"{DOMAIN}__get_history"
    description = (
        "Get the dishes eaten in past weeks, most recent first. Use it to answer 'when did we last eat...' "
        "or to suggest dishes not eaten for a while."
    )
    parameters = vol.Schema(
        {
            vol.Optional("dish", description="Only dishes matching this name"): str,
            vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
        }
    )

    async def _executer(self, planificateur: Planificateur, arguments: dict[str, Any]) -> JsonObjectType:
        return {"history": planificateur.historique(arguments.get("dish"), arguments["limit"])}


@callback
def async_get_tools(hass: HomeAssistant, llm_context: LLMContext, api_id: str) -> LLMTools | None:
    """Outils Cookbook Menu pour l'API Assist, si l'intégration est configurée."""
    if api_id != LLM_API_ASSIST or _planificateur(hass) is None:
        return None
    return LLMTools(
        tools=[ChercherRecettes(), AjouterAuMenu(), RetirerDuMenu(), LireMenu(), LireHistorique()],
        prompt=CONSIGNE,
    )
