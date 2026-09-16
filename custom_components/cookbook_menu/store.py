"""Stockage persistant d'une entrée : menu, état de la liste de courses, placard, historique."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

VERSION_STOCKAGE = 1
DELAI_SAUVEGARDE = 2


@dataclass(slots=True)
class PlatMenu:
    """Un plat du menu."""

    uid: str
    summary: str
    servings: int
    recipe_id: str | None = None
    day: date | None = None
    done: bool = False

    def en_dict(self) -> dict[str, Any]:
        donnees = asdict(self)
        donnees["day"] = self.day.isoformat() if self.day else None
        return donnees

    @classmethod
    def depuis_dict(cls, donnees: dict[str, Any]) -> PlatMenu:
        jour = donnees.get("day")
        return cls(
            uid=str(donnees["uid"]),
            summary=str(donnees.get("summary", "")),
            servings=max(1, int(donnees.get("servings", 1))),
            recipe_id=donnees.get("recipe_id"),
            day=date.fromisoformat(jour) if jour else None,
            done=bool(donnees.get("done", False)),
        )


@dataclass(slots=True)
class DonneesPlanificateur:
    """Tout ce qui est persisté pour une entrée."""

    menu: list[PlatMenu] = field(default_factory=list)
    # Lignes de courses ajoutées à la main : {uid, summary, description, done}.
    courses_manuelles: list[dict[str, Any]] = field(default_factory=list)
    # État des lignes calculées, par clé produit : {done, quantite_cochee}.
    etat_courses: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Clés des produits du placard signalés épuisés.
    placard_epuise: list[str] = field(default_factory=list)
    # Plats passés : {day, recipe_id, summary, servings}.
    historique: list[dict[str, Any]] = field(default_factory=list)

    def en_dict(self) -> dict[str, Any]:
        return {
            "menu": [p.en_dict() for p in self.menu],
            "courses_manuelles": self.courses_manuelles,
            "etat_courses": self.etat_courses,
            "placard_epuise": self.placard_epuise,
            "historique": self.historique,
        }

    @classmethod
    def depuis_dict(cls, donnees: dict[str, Any] | None) -> DonneesPlanificateur:
        if not donnees:
            return cls()
        return cls(
            menu=[PlatMenu.depuis_dict(p) for p in donnees.get("menu", [])],
            courses_manuelles=list(donnees.get("courses_manuelles", [])),
            etat_courses=dict(donnees.get("etat_courses", {})),
            placard_epuise=list(donnees.get("placard_epuise", [])),
            historique=list(donnees.get("historique", [])),
        )


class StockagePlanificateur:
    """Enveloppe du `Store` HA, avec sauvegarde différée."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, VERSION_STOCKAGE, f"{DOMAIN}.{entry_id}")
        self.donnees = DonneesPlanificateur()

    async def async_charger(self) -> DonneesPlanificateur:
        self.donnees = DonneesPlanificateur.depuis_dict(await self._store.async_load())
        return self.donnees

    def planifier_sauvegarde(self) -> None:
        self._store.async_delay_save(self.donnees.en_dict, DELAI_SAUVEGARDE)

    async def async_supprimer(self) -> None:
        await self._store.async_remove()
