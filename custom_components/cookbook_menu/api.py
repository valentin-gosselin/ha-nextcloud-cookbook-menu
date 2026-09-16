"""Client HTTP minimal pour l'API publique de Nextcloud Cookbook.

Référence : https://nextcloud.github.io/cookbook/dev/api/ (authentification basique
avec un mot de passe d'application Nextcloud).
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

API_PREFIX = "/apps/cookbook/api/v1"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class CookbookError(Exception):
    """Erreur générique du client Cookbook."""


class CookbookConnectionError(CookbookError):
    """Serveur injoignable ou réponse inexploitable."""


class CookbookAuthError(CookbookError):
    """Identifiants refusés (401 ou 403)."""


class CookbookNotFoundError(CookbookError):
    """Ressource absente, ou application Cookbook non installée (404)."""


@dataclass(frozen=True, slots=True)
class RecipeStub:
    """Résumé d'une recette tel que renvoyé par la liste."""

    id: str
    name: str
    date_modified: datetime | None


@dataclass(frozen=True, slots=True)
class Recipe:
    """Recette complète, réduite aux champs utiles à l'intégration."""

    id: str
    name: str
    category: str | None
    servings: int
    ingredients: tuple[str, ...]
    keywords: tuple[str, ...] = field(default_factory=tuple)
    date_modified: datetime | None = None
    url: str | None = None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_servings(value: Any) -> int:
    """`recipeYield` est un entier selon l'API, mais les imports anciens peuvent contenir du texte."""
    if isinstance(value, bool):
        return 1
    if isinstance(value, int | float):
        return max(1, int(value))
    if isinstance(value, str):
        chiffres = "".join(c for c in value if c.isdigit())
        if chiffres:
            return max(1, int(chiffres))
    return 1


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
    """Construit une `Recipe` à partir de la réponse JSON de `/recipes/{id}`."""
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
    )


class CookbookClient:
    """Accès en lecture à Nextcloud Cookbook."""

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
        """Ferme la session HTTP dédiée."""
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

    async def async_get_categories(self) -> list[str]:
        """Noms des catégories connues (sans l'entrée « * » des recettes non classées)."""
        data = await self._get("/categories")
        if not isinstance(data, list):
            raise CookbookConnectionError("Format inattendu pour /categories")
        return sorted(
            {str(c["name"]) for c in data if isinstance(c, dict) and c.get("name") not in (None, "*")},
            key=str.casefold,
        )

    async def async_get_recipe_stubs(self) -> list[RecipeStub]:
        """Liste résumée de toutes les recettes."""
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
        """Recette complète."""
        data = await self._get(f"/recipes/{recipe_id}")
        if not isinstance(data, dict):
            raise CookbookConnectionError(f"Format inattendu pour la recette {recipe_id}")
        return parse_recipe(data)

    async def async_get_recipes(
        self, stubs: list[RecipeStub], parallel: int, cache: dict[str, Recipe] | None = None
    ) -> dict[str, Recipe]:
        """Détails des recettes, en réutilisant le cache quand `dateModified` n'a pas bougé."""
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
                    # Supprimée entre la liste et le détail : on l'ignore.
                    return

        # gather relaie directement la première erreur (pas d'ExceptionGroup à dépiler).
        await asyncio.gather(*(charger(stub) for stub in stubs))
        return resultat
