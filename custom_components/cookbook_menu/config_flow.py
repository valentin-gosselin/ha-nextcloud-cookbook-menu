"""Flux de configuration de Cookbook Menu : ajout, réauthentification, reconfiguration et options."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import CookbookMenuConfigEntry, create_client
from .api import (
    CookbookAuthError,
    CookbookError,
    CookbookNotFoundError,
    DemandeConnexion,
    IdentifiantsNextcloud,
    async_attendre_connexion,
    async_demarrer_connexion,
)
from .const import (
    CONF_EXCLUDED_CATEGORIES,
    CONF_HISTORY_MONTHS,
    CONF_PANTRY,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SERVINGS,
    CONF_SYNC_MENU_ENTITY,
    CONF_SYNC_SHOPPING_ENTITY,
    DEFAULT_HISTORY_MONTHS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SERVINGS,
    DOMAIN,
)
from .ingredients.pantry import PLACARD_PAR_DEFAUT

_LOGGER = logging.getLogger(__name__)


def _normaliser_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _schema_url(defauts: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defauts.get(CONF_URL, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Optional(CONF_VERIFY_SSL, default=defauts.get(CONF_VERIFY_SSL, True)): bool,
        }
    )


def _schema_connexion(defauts: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defauts.get(CONF_URL, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(CONF_USERNAME, default=defauts.get(CONF_USERNAME, "")): TextSelector(),
            vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Optional(CONF_VERIFY_SSL, default=defauts.get(CONF_VERIFY_SSL, True)): bool,
        }
    )


class CookbookMenuConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flux de configuration."""

    VERSION = 1

    async def _tester(self, donnees: dict[str, Any]) -> dict[str, str]:
        """Teste la connexion (test-before-configure) et renvoie les erreurs du formulaire."""
        client = create_client(self.hass, donnees)
        try:
            await client.async_get_categories()
        except CookbookAuthError:
            return {"base": "invalid_auth"}
        except CookbookNotFoundError:
            return {"base": "cookbook_not_found"}
        except CookbookError:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Erreur inattendue pendant le test de connexion")
            return {"base": "unknown"}
        finally:
            await client.async_close()
        return {}

    def __init__(self) -> None:
        self._url: str = ""
        self._verify_ssl: bool = True
        self._demande: DemandeConnexion | None = None
        self._attente: asyncio.Task[None] | None = None
        self._identifiants: IdentifiantsNextcloud | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Première étape : l'adresse du serveur, puis le choix du mode de connexion."""
        if user_input is not None:
            self._url = _normaliser_url(user_input[CONF_URL])
            self._verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
            return await self.async_step_method()
        return self.async_show_form(step_id="user", data_schema=_schema_url({}))

    async def async_step_method(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choix : connexion dans le navigateur (recommandée) ou mot de passe d'application saisi."""
        return self.async_show_menu(step_id="method", menu_options=["login", "manual"])

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connexion dans le navigateur (Login Flow v2) : Nextcloud crée le mot de passe d'application."""
        if self._attente is None:
            session = async_get_clientsession(self.hass, verify_ssl=self._verify_ssl)
            try:
                self._demande = await async_demarrer_connexion(session, self._url)
            except CookbookNotFoundError:
                return self.async_abort(reason="login_flow_unavailable")
            except CookbookError:
                return self.async_abort(reason="cannot_connect")
            # Pas de démarrage immédiat : l'étape externe doit être affichée avant la reprise du flux.
            self._attente = self.hass.async_create_task(self._async_attendre(session), eager_start=False)
            return self.async_external_step(step_id="login", url=self._demande.url_connexion)
        return self.async_external_step_done(next_step_id="login_done")

    async def _async_attendre(self, session: Any) -> None:
        assert self._demande is not None
        self._identifiants = await async_attendre_connexion(session, self._demande)
        self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(flow_id=self.flow_id), eager_start=False
        )

    @callback
    def async_remove(self) -> None:
        """Flux abandonné (fenêtre fermée) : on arrête d'interroger Nextcloud."""
        if self._attente is not None and not self._attente.done():
            self._attente.cancel()

    async def async_step_login_done(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Accès accordé (ou délai expiré) : on vérifie puis on enregistre."""
        if self._identifiants is None:
            return self.async_abort(reason="login_timeout")
        donnees = {
            CONF_URL: _normaliser_url(self._identifiants.url),
            CONF_USERNAME: self._identifiants.utilisateur,
            CONF_PASSWORD: self._identifiants.mot_de_passe,
            CONF_VERIFY_SSL: self._verify_ssl,
        }
        if errors := await self._tester(donnees):
            return self.async_abort(reason=errors["base"])
        return await self._async_enregistrer(donnees)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Saisie manuelle d'un utilisateur et d'un mot de passe d'application."""
        errors: dict[str, str] = {}
        if user_input is not None:
            donnees = {**user_input, CONF_URL: self._url, CONF_VERIFY_SSL: self._verify_ssl}
            if not (errors := await self._tester(donnees)):
                return await self._async_enregistrer(donnees)
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): TextSelector(),
                        vol.Required(CONF_PASSWORD): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.PASSWORD)
                        ),
                    }
                ),
                {CONF_USERNAME: user_input[CONF_USERNAME]} if user_input else {},
            ),
            description_placeholders={CONF_URL: self._url},
            errors=errors,
        )

    async def _async_enregistrer(self, donnees: dict[str, Any]) -> ConfigFlowResult:
        """Crée l'entrée, ou met à jour celle en cours de réauthentification (même compte exigé)."""
        await self.async_set_unique_id(f"{donnees[CONF_URL]}|{donnees[CONF_USERNAME]}".casefold())
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=donnees)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"{donnees[CONF_USERNAME]} @ {donnees[CONF_URL].split('://', 1)[-1]}", data=donnees
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Mot de passe d'application refusé : nouvelle connexion ou nouveau mot de passe."""
        self._url = entry_data[CONF_URL]
        self._verify_ssl = entry_data.get(CONF_VERIFY_SSL, True)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choix : se reconnecter avec Nextcloud ou saisir un nouveau mot de passe d'application."""
        entree = self._get_reauth_entry()
        return self.async_show_menu(
            step_id="reauth_confirm",
            menu_options=["login", "reauth_manual"],
            description_placeholders={
                CONF_USERNAME: entree.data[CONF_USERNAME],
                CONF_URL: entree.data[CONF_URL],
            },
        )

    async def async_step_reauth_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Nouveau mot de passe d'application saisi à la main."""
        entree = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            donnees = {**entree.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            if not (errors := await self._tester(donnees)):
                return self.async_update_reload_and_abort(entree, data=donnees)
        return self.async_show_form(
            step_id="reauth_manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={
                CONF_USERNAME: entree.data[CONF_USERNAME],
                CONF_URL: entree.data[CONF_URL],
            },
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Changement d'URL, d'utilisateur ou de mot de passe."""
        entree = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = _normaliser_url(user_input[CONF_URL])
            await self.async_set_unique_id(f"{user_input[CONF_URL]}|{user_input[CONF_USERNAME]}".casefold())
            if self.source == SOURCE_RECONFIGURE and self.unique_id != entree.unique_id:
                self._abort_if_unique_id_configured()
            if not (errors := await self._tester(user_input)):
                return self.async_update_reload_and_abort(entree, unique_id=self.unique_id, data=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _schema_connexion(entree.data),
                user_input or {k: v for k, v in entree.data.items() if k != CONF_PASSWORD},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CookbookMenuConfigEntry) -> CookbookMenuOptionsFlow:
        """Flux d'options."""
        return CookbookMenuOptionsFlow()


class CookbookMenuOptionsFlow(OptionsFlowWithReload):
    """Réglages du foyer : couverts, catégories exclues, rafraîchissement."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Formulaire unique d'options."""
        if user_input is not None:
            user_input[CONF_SERVINGS] = int(user_input[CONF_SERVINGS])
            user_input[CONF_SCAN_INTERVAL_MINUTES] = int(user_input[CONF_SCAN_INTERVAL_MINUTES])
            user_input[CONF_HISTORY_MONTHS] = int(user_input[CONF_HISTORY_MONTHS])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        categories: list[str] = []
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is not None:
            try:
                categories = await runtime.client.async_get_categories()
            except CookbookError:
                _LOGGER.debug("Catégories indisponibles pour le formulaire d'options")
        choix = sorted({*categories, *options.get(CONF_EXCLUDED_CATEGORIES, [])}, key=str.casefold)
        placard = options.get(CONF_PANTRY, list(PLACARD_PAR_DEFAUT))
        nos_listes = [
            e.entity_id
            for e in er.async_entries_for_config_entry(er.async_get(self.hass), self.config_entry.entry_id)
        ]
        selecteur_liste = EntitySelector(EntitySelectorConfig(domain="todo", exclude_entities=nos_listes))
        choix_placard = list(dict.fromkeys([*PLACARD_PAR_DEFAUT, *placard]))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SERVINGS, default=options.get(CONF_SERVINGS, DEFAULT_SERVINGS)
                ): NumberSelector(NumberSelectorConfig(min=1, max=30, step=1, mode=NumberSelectorMode.BOX)),
                vol.Optional(
                    CONF_EXCLUDED_CATEGORIES, default=options.get(CONF_EXCLUDED_CATEGORIES, [])
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=choix, multiple=True, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(CONF_PANTRY, default=placard): SelectSelector(
                    SelectSelectorConfig(
                        options=choix_placard,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SYNC_MENU_ENTITY,
                    description={"suggested_value": options.get(CONF_SYNC_MENU_ENTITY)},
                ): selecteur_liste,
                vol.Optional(
                    CONF_SYNC_SHOPPING_ENTITY,
                    description={"suggested_value": options.get(CONF_SYNC_SHOPPING_ENTITY)},
                ): selecteur_liste,
                vol.Required(
                    CONF_HISTORY_MONTHS, default=options.get(CONF_HISTORY_MONTHS, DEFAULT_HISTORY_MONTHS)
                ): NumberSelector(NumberSelectorConfig(min=1, max=120, step=1, mode=NumberSelectorMode.BOX)),
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES),
                ): NumberSelector(NumberSelectorConfig(min=5, max=1440, step=5, mode=NumberSelectorMode.BOX)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
