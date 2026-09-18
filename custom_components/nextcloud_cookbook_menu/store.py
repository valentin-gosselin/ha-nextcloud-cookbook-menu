"""Stockage persistant d'une entrée : menu, état de la liste de courses, placard, historique."""

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
# Le domaine s'appelait « cookbook_menu » avant la 1.0.0.
ANCIEN_DOMAINE = "cookbook_menu"

_LOGGER = logging.getLogger(__name__)


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
    # Produits rangés au placard à la main, en plus des options : clé produit -> nom.
    placard_ajouts: dict[str, str] = field(default_factory=dict)
    # Produits des options sortis du placard depuis la carte : clés.
    placard_retires: list[str] = field(default_factory=list)
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
            "placard_ajouts": self.placard_ajouts,
            "placard_retires": self.placard_retires,
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
        placard_ajouts = dict(donnees.get("placard_ajouts", {}))
        placard_epuise = dict(donnees.get("placard_epuise", {}))
        # Migration : un produit de placard rangé en « maison » avant l'index rejoint le placard.
        for cle_produit in [c for c in maison if est_produit_de_placard(c)]:
            produit = maison.pop(cle_produit)
            placard_ajouts.setdefault(cle_produit, produit["nom"])
            if not produit.get("present"):
                placard_epuise.setdefault(cle_produit, produit["nom"])
        return cls(
            menu=[PlatMenu.depuis_dict(p) for p in donnees.get("menu", [])],
            placard_epuise=placard_epuise,
            placard_ajouts=placard_ajouts,
            placard_retires=list(donnees.get("placard_retires", [])),
            frigo=dict(donnees.get("frigo", {})),
            maison=maison,
            placard_verifie=bool(donnees.get("placard_verifie", False)),
            historique=list(donnees.get("historique", [])),
            synchro=dict(donnees.get("synchro", {})),
        )


class StockagePlanificateur:
    """Enveloppe du `Store` HA, avec sauvegarde différée."""

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
        """Reprend le menu et la réserve laissés par le domaine « cookbook_menu » (avant la 1.0.0).

        Une seule entrée était possible en pratique : le fichier est repris s'il est unique.
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
