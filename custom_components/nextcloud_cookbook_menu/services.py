"""Service actions: menu control for automations, scripts, and voice."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent, service
from homeassistant.util import dt as dt_util

from .const import CONF_TIMER_DEVICE, CONF_TIMER_ENTITY, DOMAIN, EVENEMENT_MINUTEUR
from .jours import lire_jour
from .planner import INCHANGE, Planificateur

ATTR_RECIPE = "recipe"
ATTR_DAY = "day"
ATTR_SERVINGS = "servings"
ATTR_UID = "uid"
ATTR_QUERY = "query"
ATTR_LIMIT = "limit"
ATTR_RECIPE_ID = "recipe_id"

SERVICE_ADD_TO_MENU = "add_to_menu"
SERVICE_REMOVE_FROM_MENU = "remove_from_menu"
SERVICE_SET_SERVINGS = "set_servings"
SERVICE_NEW_WEEK = "new_week"
SERVICE_SEARCH_RECIPES = "search_recipes"
SERVICE_GET_HISTORY = "get_history"
SERVICE_OUT_OF_STOCK = "out_of_stock"
SERVICE_START_TIMER = "start_timer"
SERVICE_STOP_TIMER = "stop_timer"
ATTR_TIMER = "timer"
ATTR_PRODUCT = "product"
ATTR_NAME = "name"
ATTR_SECONDS = "seconds"

_ENTREE = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
_COUVERTS = vol.All(vol.Coerce(int), vol.Range(min=1, max=50))

SCHEMA_ADD = vol.Schema(
    {
        **_ENTREE,
        vol.Required(ATTR_RECIPE): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_DAY): vol.Any(cv.date, cv.string),
        vol.Optional(ATTR_SERVINGS): _COUVERTS,
        vol.Optional(ATTR_RECIPE_ID): cv.string,
    }
)
SCHEMA_CIBLE = {
    **_ENTREE,
    vol.Exclusive(ATTR_RECIPE, "cible"): cv.string,
    vol.Exclusive(ATTR_UID, "cible"): cv.string,
}
SCHEMA_REMOVE = vol.All(vol.Schema(SCHEMA_CIBLE), cv.has_at_least_one_key(ATTR_RECIPE, ATTR_UID))
SCHEMA_SERVINGS = vol.All(
    vol.Schema({**SCHEMA_CIBLE, vol.Required(ATTR_SERVINGS): _COUVERTS}),
    cv.has_at_least_one_key(ATTR_RECIPE, ATTR_UID),
)
SCHEMA_NEW_WEEK = vol.Schema(_ENTREE)
SCHEMA_HISTORY = vol.Schema(
    {
        **_ENTREE,
        vol.Optional(ATTR_RECIPE): cv.string,
        vol.Optional(ATTR_LIMIT, default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
    }
)
SCHEMA_OUT_OF_STOCK = vol.Schema({**_ENTREE, vol.Required(ATTR_PRODUCT): vol.All(cv.string, vol.Length(min=1))})
SCHEMA_START_TIMER = vol.Schema(
    {
        **_ENTREE,
        vol.Required(ATTR_SECONDS): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 3600)),
        vol.Optional(ATTR_NAME): cv.string,
    }
)
SCHEMA_STOP_TIMER = vol.Schema(
    {
        **_ENTREE,
        vol.Exclusive(ATTR_TIMER, "cible"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Exclusive(ATTR_NAME, "cible"): cv.string,
    }
)
SCHEMA_SEARCH = vol.Schema(
    {
        **_ENTREE,
        vol.Required(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_LIMIT, default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
    }
)


def _planificateur(appel: ServiceCall) -> Planificateur:
    entree = service.async_get_config_entry(appel.hass, DOMAIN, appel.data.get(ATTR_CONFIG_ENTRY_ID))
    return entree.runtime_data.planner


def _jour(appel: ServiceCall) -> Any:
    if ATTR_DAY not in appel.data:
        return None
    try:
        return lire_jour(appel.data[ATTR_DAY], dt_util.now().date())
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_day",
            translation_placeholders={"day": str(appel.data[ATTR_DAY])},
        ) from err


def _uid_du_plat(planificateur: Planificateur, appel: ServiceCall) -> str:
    if ATTR_UID in appel.data:
        return appel.data[ATTR_UID]
    return planificateur.plat_par_nom(appel.data[ATTR_RECIPE]).uid


async def _ajouter(appel: ServiceCall) -> ServiceResponse:
    return _planificateur(appel).async_ajouter_au_menu(
        appel.data[ATTR_RECIPE],
        jour=_jour(appel),
        couverts=appel.data.get(ATTR_SERVINGS),
        recipe_id=appel.data.get(ATTR_RECIPE_ID),
    )


async def _retirer(appel: ServiceCall) -> None:
    planificateur = _planificateur(appel)
    planificateur.async_supprimer_plats([_uid_du_plat(planificateur, appel)])


async def _couverts(appel: ServiceCall) -> None:
    planificateur = _planificateur(appel)
    planificateur.async_modifier_plat(
        _uid_du_plat(planificateur, appel), jour=INCHANGE, couverts=appel.data[ATTR_SERVINGS]
    )


async def _nouvelle_semaine(appel: ServiceCall) -> ServiceResponse:
    archives = _planificateur(appel).async_nouvelle_semaine(dt_util.now().date())
    return {"archived": archives}


async def _historique(appel: ServiceCall) -> ServiceResponse:
    planificateur = _planificateur(appel)
    return {"history": planificateur.historique(appel.data.get(ATTR_RECIPE), appel.data[ATTR_LIMIT])}


async def _manque(appel: ServiceCall) -> None:
    _planificateur(appel).async_ajouter_course(appel.data[ATTR_PRODUCT])


def _entites_minuteur(entree: Any) -> list[str]:
    """The option only accepted a single timer entity before 1.3.0."""
    valeur = entree.options.get(CONF_TIMER_ENTITY)
    if not valeur:
        return []
    return [valeur] if isinstance(valeur, str) else list(valeur)


async def _minuteur(appel: ServiceCall) -> ServiceResponse:
    """Starts a timer: integration sensor, timer entity, voice device, event."""
    hass = appel.hass
    entree = service.async_get_config_entry(hass, DOMAIN, appel.data.get(ATTR_CONFIG_ENTRY_ID))
    gestionnaire = entree.runtime_data.timers
    secondes = appel.data[ATTR_SECONDS]
    nom = appel.data.get(ATTR_NAME) or ""
    # First idle timer entity that isn't already claimed by another timer in progress.
    occupees = {m.entite for m in gestionnaire.minuteurs if not m.libre}
    entite = next(
        (
            e
            for e in _entites_minuteur(entree)
            if e not in occupees and (etat := hass.states.get(e)) and etat.state == "idle"
        ),
        None,
    )
    numero = gestionnaire.async_demarrer(nom, secondes, entite)
    hass.bus.async_fire(
        EVENEMENT_MINUTEUR,
        {
            "config_entry_id": entree.entry_id,
            "name": nom,
            "seconds": secondes,
            "timer": numero,
            "entity_id": entite,
        },
    )
    if entite:
        await hass.services.async_call(
            "timer",
            "start",
            {"entity_id": entite, "duration": str(timedelta(seconds=secondes))},
            blocking=True,
        )
    if appareil := entree.options.get(CONF_TIMER_DEVICE):
        try:
            await intent.async_handle(
                hass,
                DOMAIN,
                intent.INTENT_START_TIMER,
                {"seconds": {"value": secondes}, **({"name": {"value": nom}} if nom else {})},
                device_id=appareil,
                language=hass.config.language,
            )
        except intent.IntentError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="timer_device_unsupported",
                translation_placeholders={"error": str(err)},
            ) from err
    return {"timer": numero, "entity_id": entite}


async def _arreter_minuteur(appel: ServiceCall) -> None:
    """Stops a timer of the integration (or all of them), and the timer entity it was occupying."""
    hass = appel.hass
    entree = service.async_get_config_entry(hass, DOMAIN, appel.data.get(ATTR_CONFIG_ENTRY_ID))
    gestionnaire = entree.runtime_data.timers
    if ATTR_TIMER in appel.data:
        numeros = [appel.data[ATTR_TIMER]]
    elif nom := appel.data.get(ATTR_NAME):
        # The card stops a timer by name when it did not get its number back.
        numeros = [i + 1 for i, m in enumerate(gestionnaire.minuteurs) if m.nom == nom]
    else:
        numeros = list(range(1, len(gestionnaire.minuteurs) + 1))
    for numero in numeros:
        if (minuteur := gestionnaire.async_arreter(numero)) and minuteur.entite:
            await hass.services.async_call("timer", "cancel", {"entity_id": minuteur.entite}, blocking=True)


async def _chercher(appel: ServiceCall) -> ServiceResponse:
    planificateur = _planificateur(appel)
    return {
        "recipes": [
            {
                "id": c.recette.id,
                "name": c.recette.name,
                "category": c.recette.category,
                "servings": c.recette.servings,
                "score": c.score,
            }
            for c in planificateur.chercher_recettes(appel.data[ATTR_QUERY], appel.data[ATTR_LIMIT])
        ]
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Registers the actions (once per domain, per the action-setup rule)."""
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_TO_MENU, _ajouter, schema=SCHEMA_ADD, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_FROM_MENU, _retirer, schema=SCHEMA_REMOVE)
    hass.services.async_register(DOMAIN, SERVICE_SET_SERVINGS, _couverts, schema=SCHEMA_SERVINGS)
    hass.services.async_register(
        DOMAIN,
        SERVICE_NEW_WEEK,
        _nouvelle_semaine,
        schema=SCHEMA_NEW_WEEK,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_OUT_OF_STOCK, _manque, schema=SCHEMA_OUT_OF_STOCK)
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_TIMER,
        _minuteur,
        schema=SCHEMA_START_TIMER,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP_TIMER, _arreter_minuteur, schema=SCHEMA_STOP_TIMER)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        _historique,
        schema=SCHEMA_HISTORY,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_RECIPES,
        _chercher,
        schema=SCHEMA_SEARCH,
        supports_response=SupportsResponse.ONLY,
    )
