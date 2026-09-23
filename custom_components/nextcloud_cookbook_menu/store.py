"""Persistent storage for a config entry: menu, shopping list state, pantry, history."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ingredients.catalogue_placard import est_produit_de_placard
from .ingredients.normalize import cle

VERSION_STOCKAGE = 1
DELAI_SAUVEGARDE = 2
# The domain was called "cookbook_menu" before 1.0.0.
ANCIEN_DOMAINE = "cookbook_menu"

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PlatMenu:
    """A dish in the menu."""

    uid: str
    summary: str
    servings: int
    recipe_id: str | None = None
    day: date | None = None
    done: bool = False
    # Its share of ingredients has already been removed from the fridge (dish cooked or date past).
    consumed: bool = False

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
            consumed=bool(donnees.get("consumed", False)),
        )


@dataclass(slots=True)
class DonneesPlanificateur:
    """Everything persisted for a config entry."""

    menu: list[PlatMenu] = field(default_factory=list)
    # Pantry products reported missing: product key -> entered name.
    placard_epuise: dict[str, str] = field(default_factory=dict)
    # Products stocked in the pantry by hand, on top of the options: product key -> name.
    placard_ajouts: dict[str, str] = field(default_factory=dict)
    # Option products taken out of the pantry from the card: keys.
    placard_retires: list[str] = field(default_factory=list)
    # Fridge: product key -> {name, quantities {unit: value}, expiry (ISO date)}.
    frigo: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Household (outside the menu and the pantry): key -> {name, present (bool), description}.
    maison: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Recurring products (butter for toast): key -> {name, weeks, last_purchase}.
    recurrents: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Dates of the last purchases per product, to suggest recurrences.
    achats: dict[str, list[str]] = field(default_factory=dict)
    # The pantry has been checked for the first time in the card.
    placard_verifie: bool = False
    # Past dishes: {day, recipe_id, summary, servings}.
    historique: list[dict[str, Any]] = field(default_factory=list)
    # Sync: target entity -> our uid -> {target uid, last pushed state}.
    synchro: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def en_dict(self) -> dict[str, Any]:
        return {
            "menu": [p.en_dict() for p in self.menu],
            "placard_epuise": self.placard_epuise,
            "placard_ajouts": self.placard_ajouts,
            "placard_retires": self.placard_retires,
            "frigo": self.frigo,
            "maison": self.maison,
            "recurrents": self.recurrents,
            "achats": self.achats,
            "placard_verifie": self.placard_verifie,
            "historique": self.historique,
            "synchro": self.synchro,
        }

    @classmethod
    def depuis_dict(cls, donnees: dict[str, Any] | None) -> DonneesPlanificateur:
        if not donnees:
            return cls()
        maison = dict(donnees.get("maison", {}))
        # Migration: old manual lines become "maison" (household) products.
        for manuelle in donnees.get("courses_manuelles", []):
            nom = str(manuelle.get("summary", "")).strip()
            if nom:
                maison.setdefault(
                    cle(nom),
                    {
                        "nom": nom,
                        "present": bool(manuelle.get("done")),
                        "description": manuelle.get("description"),
                    },
                )
        placard_ajouts = dict(donnees.get("placard_ajouts", {}))
        placard_epuise = dict(donnees.get("placard_epuise", {}))
        # Migration: a pantry product stocked under "maison" before the index rejoins the pantry.
        for cle_produit in [c for c in maison if est_produit_de_placard(c)]:
            produit = maison.pop(cle_produit)
            placard_ajouts.setdefault(cle_produit, produit["nom"])
            if not produit.get("present"):
                placard_epuise.setdefault(cle_produit, produit["nom"])
        frigo = dict(donnees.get("frigo", {}))
        # Migration: a shelf-stable product, bought for the menu, used to be stored in the fridge.
        for cle_produit in [c for c in frigo if est_produit_de_placard(c)]:
            placard_ajouts.setdefault(cle_produit, frigo.pop(cle_produit)["nom"])
        return cls(
            menu=[PlatMenu.depuis_dict(p) for p in donnees.get("menu", [])],
            placard_epuise=placard_epuise,
            placard_ajouts=placard_ajouts,
            placard_retires=list(donnees.get("placard_retires", [])),
            frigo=frigo,
            maison=maison,
            recurrents=dict(donnees.get("recurrents", {})),
            achats=dict(donnees.get("achats", {})),
            placard_verifie=bool(donnees.get("placard_verifie", False)),
            historique=list(donnees.get("historique", [])),
            synchro=dict(donnees.get("synchro", {})),
        )


class StockagePlanificateur:
    """Wrapper around HA's `Store`, with delayed saving."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, VERSION_STOCKAGE, f"{DOMAIN}.{entry_id}")
        self.donnees = DonneesPlanificateur()

    async def async_charger(self) -> DonneesPlanificateur:
        brut = await self._store.async_load()
        if brut is None and (ancien := await self._async_lire_ancien_domaine()) is not None:
            brut = ancien
            self.planifier_sauvegarde()
        self.donnees = DonneesPlanificateur.depuis_dict(brut)
        return self.donnees

    async def _async_lire_ancien_domaine(self) -> dict[str, Any] | None:
        """Recover the menu and stock left by the "cookbook_menu" domain (before 1.0.0).

        Only one entry was possible in practice: the file is picked up if it is unique.
        """
        dossier = Path(self._hass.config.path(".storage"))

        def lire() -> dict[str, Any] | None:
            fichiers = sorted(dossier.glob(f"{ANCIEN_DOMAINE}.*"))
            if len(fichiers) != 1:
                return None
            return json.loads(fichiers[0].read_text(encoding="utf-8"))

        try:
            contenu = await self._hass.async_add_executor_job(lire)
        except (OSError, ValueError) as err:
            _LOGGER.warning("Données de l'ancien domaine illisibles : %s", err)
            return None
        if contenu is None:
            return None
        _LOGGER.info("Menu et réserve repris depuis l'ancien domaine %s", ANCIEN_DOMAINE)
        return contenu.get("data")

    def planifier_sauvegarde(self) -> None:
        self._store.async_delay_save(self.donnees.en_dict, DELAI_SAUVEGARDE)

    async def async_supprimer(self) -> None:
        await self._store.async_remove()
