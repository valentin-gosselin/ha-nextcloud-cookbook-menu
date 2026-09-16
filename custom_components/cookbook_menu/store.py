"""Stockage persistant d'une entrée : menu, état de la liste de courses, placard, historique."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ingredients.normalize import cle

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
    # Sa part d'ingrédients a déjà été retirée du frigo (plat cuisiné ou date passée).
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
    """Tout ce qui est persisté pour une entrée."""

    menu: list[PlatMenu] = field(default_factory=list)
    # Produits du placard signalés manquants : clé produit -> nom saisi.
    placard_epuise: dict[str, str] = field(default_factory=dict)
    # Frigo : clé produit -> {nom, quantites {mesure: valeur}, expire (date ISO)}.
    frigo: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Maison (hors menu et hors placard) : clé -> {nom, present (bool), description}.
    maison: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Le placard a été vérifié une première fois dans la carte.
    placard_verifie: bool = False
    # Plats passés : {day, recipe_id, summary, servings}.
    historique: list[dict[str, Any]] = field(default_factory=list)
    # Synchronisation : entité cible -> notre uid -> {uid cible, dernier état poussé}.
    synchro: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def en_dict(self) -> dict[str, Any]:
        return {
            "menu": [p.en_dict() for p in self.menu],
            "placard_epuise": self.placard_epuise,
            "frigo": self.frigo,
            "maison": self.maison,
            "placard_verifie": self.placard_verifie,
            "historique": self.historique,
            "synchro": self.synchro,
        }

    @classmethod
    def depuis_dict(cls, donnees: dict[str, Any] | None) -> DonneesPlanificateur:
        if not donnees:
            return cls()
        maison = dict(donnees.get("maison", {}))
        # Migration : les anciennes lignes manuelles deviennent des produits « maison ».
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
        return cls(
            menu=[PlatMenu.depuis_dict(p) for p in donnees.get("menu", [])],
            placard_epuise=dict(donnees.get("placard_epuise", {})),
            frigo=dict(donnees.get("frigo", {})),
            maison=maison,
            placard_verifie=bool(donnees.get("placard_verifie", False)),
            historique=list(donnees.get("historique", [])),
            synchro=dict(donnees.get("synchro", {})),
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
