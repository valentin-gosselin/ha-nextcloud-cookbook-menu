"""Minimal HTTP client for the public Nextcloud Cookbook API.

Reference: https://nextcloud.github.io/cookbook/dev/api/ (basic authentication
with a Nextcloud app password).
"""

from __future__ import annotations

import asyncio
import base64
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

API_PREFIX = "/apps/cookbook/api/v1"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class CookbookError(Exception):
    """Generic error from the Cookbook client."""


class CookbookConnectionError(CookbookError):
    """Server unreachable or response could not be processed."""


class CookbookAuthError(CookbookError):
    """Credentials rejected (401 or 403)."""


class CookbookNotFoundError(CookbookError):
    """Resource missing, or the Cookbook app is not installed (404)."""


@dataclass(frozen=True, slots=True)
class RecipeStub:
    """Recipe summary as returned by the list."""

    id: str
    name: str
    date_modified: datetime | None


@dataclass(frozen=True, slots=True)
class Recipe:
    """Full recipe, trimmed down to the fields the integration needs."""

    id: str
    name: str
    category: str | None
    servings: int
    ingredients: tuple[str, ...]
    keywords: tuple[str, ...] = field(default_factory=tuple)
    date_modified: datetime | None = None
    url: str | None = None
    description: str = ""
    instructions: tuple[str, ...] = field(default_factory=tuple)
    tools: tuple[str, ...] = field(default_factory=tuple)
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    total_minutes: int | None = None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_servings(value: Any) -> int:
    """`recipeYield` is an integer per the API, but older imports may contain text."""
    if isinstance(value, bool):
        return 1
    if isinstance(value, int | float):
        return max(1, int(value))
    if isinstance(value, str):
        chiffres = "".join(c for c in value if c.isdigit())
        if chiffres:
            return max(1, int(chiffres))
    return 1


def _parse_duree(value: Any) -> int | None:
    """ISO 8601 duration ("PT1H30M0S") in minutes, None if absent or zero."""
    if not isinstance(value, str):
        return None
    correspondance = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value.strip())
    if correspondance is None:
        return None
    jours, heures, minutes, secondes = (int(x) if x else 0 for x in correspondance.groups())
    total = jours * 1440 + heures * 60 + minutes + (1 if secondes >= 30 else 0)
    return total or None


def _textes(value: Any) -> tuple[str, ...]:
    """List of non-empty strings. Also accepts schema.org steps of the form {"text": ...}."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return ()
    resultat = []
    for element in value:
        if isinstance(element, dict):
            element = element.get("text")
        if isinstance(element, str) and element.strip():
            resultat.append(element.strip())
    return tuple(resultat)


def _parse_keywords(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    vus: dict[str, None] = {}
    for mot in value.split(","):
        mot = mot.strip()
        if mot:
            vus.setdefault(mot, None)
    return tuple(vus)


def parse_recipe(data: dict[str, Any]) -> Recipe:
    """Builds a `Recipe` from the JSON response of `/recipes/{id}`."""
    ingredients = data.get("recipeIngredient") or []
    category = data.get("recipeCategory")
    return Recipe(
        id=str(data.get("id") or data.get("recipe_id")),
        name=str(data.get("name", "")).strip(),
        category=category.strip() if isinstance(category, str) and category.strip() else None,
        servings=_parse_servings(data.get("recipeYield")),
        ingredients=tuple(str(i) for i in ingredients if isinstance(i, str)),
        keywords=_parse_keywords(data.get("keywords")),
        date_modified=_parse_datetime(data.get("dateModified")),
        url=data.get("url") or None,
        description=str(data.get("description") or "").strip(),
        instructions=_textes(data.get("recipeInstructions")),
        tools=_textes(data.get("tool")),
        prep_minutes=_parse_duree(data.get("prepTime")),
        cook_minutes=_parse_duree(data.get("cookTime")),
        total_minutes=_parse_duree(data.get("totalTime")),
    )


class CookbookClient:
    """Read-only access to Nextcloud Cookbook."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = url.rstrip("/")
        jeton = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        self._headers = {
            "Accept": "application/json",
            "OCS-APIRequest": "true",
            "Authorization": f"Basic {jeton}",
        }

    async def async_close(self) -> None:
        """Closes the dedicated HTTP session."""
        await self._session.close()

    async def _get(self, path: str) -> Any:
        try:
            async with self._session.get(
                f"{self._base}{API_PREFIX}{path}",
                headers=self._headers,
                timeout=TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise CookbookAuthError(f"Accès refusé ({response.status})")
                if response.status == 404:
                    raise CookbookNotFoundError(path)
                if response.status >= 400:
                    raise CookbookConnectionError(f"Réponse HTTP {response.status} sur {path}")
                try:
                    return await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise CookbookConnectionError(f"Réponse non JSON sur {path}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CookbookConnectionError(str(err) or type(err).__name__) from err

    async def async_get_image(self, recipe_id: str, taille: str = "full") -> tuple[bytes, str] | None:
        """Recipe photo (bytes, MIME type), None if the recipe doesn't have one."""
        try:
            async with self._session.get(
                f"{self._base}{API_PREFIX}/recipes/{recipe_id}/image",
                params={"size": taille},
                headers={k: v for k, v in self._headers.items() if k != "Accept"},
                timeout=TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise CookbookAuthError(f"Accès refusé ({response.status})")
                if response.status >= 400:
                    return None
                type_mime = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
                if not type_mime.startswith("image/"):
                    return None
                return await response.read(), type_mime
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CookbookConnectionError(str(err) or type(err).__name__) from err

    async def async_get_categories(self) -> list[str]:
        """Names of known categories (excluding the "*" entry for unclassified recipes)."""
        data = await self._get("/categories")
        if not isinstance(data, list):
            raise CookbookConnectionError("Format inattendu pour /categories")
        return sorted(
            {str(c["name"]) for c in data if isinstance(c, dict) and c.get("name") not in (None, "*")},
            key=str.casefold,
        )

    async def async_get_recipe_stubs(self) -> list[RecipeStub]:
        """Summary list of all recipes."""
        data = await self._get("/recipes")
        if not isinstance(data, list):
            raise CookbookConnectionError("Format inattendu pour /recipes")
        return [
            RecipeStub(
                id=str(item.get("id") or item.get("recipe_id")),
                name=str(item.get("name", "")).strip(),
                date_modified=_parse_datetime(item.get("dateModified")),
            )
            for item in data
            if isinstance(item, dict) and (item.get("id") or item.get("recipe_id"))
        ]

    async def async_get_recipe(self, recipe_id: str) -> Recipe:
        """Full recipe."""
        data = await self._get(f"/recipes/{recipe_id}")
        if not isinstance(data, dict):
            raise CookbookConnectionError(f"Format inattendu pour la recette {recipe_id}")
        return parse_recipe(data)

    async def async_get_recipes(
        self, stubs: list[RecipeStub], parallel: int, cache: dict[str, Recipe] | None = None
    ) -> dict[str, Recipe]:
        """Recipe details, reusing the cache when `dateModified` hasn't changed."""
        cache = cache or {}
        semaphore = asyncio.Semaphore(parallel)
        resultat: dict[str, Recipe] = {}

        async def charger(stub: RecipeStub) -> None:
            connue = cache.get(stub.id)
            if connue is not None and connue.date_modified == stub.date_modified:
                resultat[stub.id] = connue
                return
            async with semaphore:
                try:
                    resultat[stub.id] = await self.async_get_recipe(stub.id)
                except CookbookNotFoundError:
                    # Deleted between the list and the detail fetch: skip it.
                    return

        # gather re-raises the first error directly (no ExceptionGroup to unwrap).
        await asyncio.gather(*(charger(stub) for stub in stubs))
        return resultat


# --- Nextcloud Login Flow v2 ------------------------------------------------------------
# https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html#login-flow-v2
# The user logs in through their browser and grants access; Nextcloud then creates an app
# password named after the User-Agent, which we retrieve by polling "poll".

AGENT_CONNEXION = "Nextcloud Cookbook Menu (Home Assistant)"


@dataclass(frozen=True, slots=True)
class DemandeConnexion:
    """Pending connection: page to open and polling token."""

    url_connexion: str
    url_poll: str
    jeton: str


@dataclass(frozen=True, slots=True)
class IdentifiantsNextcloud:
    """Credentials returned by Nextcloud once access is granted."""

    url: str
    utilisateur: str
    mot_de_passe: str


async def async_demarrer_connexion(session: aiohttp.ClientSession, url: str) -> DemandeConnexion:
    """Opens a Login Flow v2 request."""
    try:
        async with session.post(
            f"{url.rstrip('/')}/index.php/login/v2", headers={"User-Agent": AGENT_CONNEXION}, timeout=TIMEOUT
        ) as reponse:
            if reponse.status == 404:
                raise CookbookNotFoundError("login/v2")
            if reponse.status >= 400:
                raise CookbookConnectionError(f"Réponse HTTP {reponse.status} sur login/v2")
            donnees = await reponse.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise CookbookConnectionError(str(err) or type(err).__name__) from err
    try:
        return DemandeConnexion(
            url_connexion=donnees["login"],
            url_poll=donnees["poll"]["endpoint"],
            jeton=donnees["poll"]["token"],
        )
    except (KeyError, TypeError) as err:
        raise CookbookConnectionError("Réponse login/v2 inattendue") from err


async def async_attendre_connexion(
    session: aiohttp.ClientSession,
    demande: DemandeConnexion,
    intervalle: float = 2.0,
    duree_max: float = 1200.0,
) -> IdentifiantsNextcloud | None:
    """Polls Nextcloud until access is granted. None if the timeout expires."""
    ecoule = 0.0
    while ecoule < duree_max:
        try:
            async with session.post(
                demande.url_poll,
                data={"token": demande.jeton},
                headers={"User-Agent": AGENT_CONNEXION},
                timeout=TIMEOUT,
            ) as reponse:
                if reponse.status == 200:
                    donnees = await reponse.json(content_type=None)
                    return IdentifiantsNextcloud(
                        url=str(donnees["server"]).rstrip("/"),
                        utilisateur=str(donnees["loginName"]),
                        mot_de_passe=str(donnees["appPassword"]),
                    )
        except aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError:
            # Transient outage: keep waiting until the timeout.
            pass
        await asyncio.sleep(intervalle)
        ecoule += intervalle
    return None
