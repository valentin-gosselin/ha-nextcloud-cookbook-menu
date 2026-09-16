"""Planificateur : source de vérité du menu (et, ensuite, des courses et du placard).

Les entités todo, les actions de service et les outils vocaux passent tous par ici :
aucune logique métier n'est dupliquée ailleurs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError

from .api import Recipe
from .const import CONF_SERVINGS, DEFAULT_SERVINGS, DOMAIN
from .ingredients.shopping import Contribution, LigneCourses, augmentation, calculer, formater_quantites
from .matching import Correspondance, chercher, est_ambigu, lien_automatique
from .store import PlatMenu, StockagePlanificateur

if TYPE_CHECKING:
    from .coordinator import CookbookCoordinator

# Valeur sentinelle : « ne pas modifier ce champ » (None a un sens pour la date).
INCHANGE: Final = object()

PREFIXE_PRODUIT: Final = "produit:"

_COUVERTS = re.compile(
    r"^\s*(?:pour\s+)?(?P<n>\d{1,2})\s*(?:couverts?|personnes?|pers\.?|parts?|portions?|servings?|people)?\s*$",
    re.IGNORECASE,
)


def lire_couverts(texte: str | None) -> int | None:
    """Nombre de couverts écrit librement (« pour 4 », « 4 couverts », « 4 »)."""
    if not texte:
        return None
    premiere_partie = texte.split(",")[0]
    correspondance = _COUVERTS.match(premiere_partie)
    if correspondance is None:
        return None
    nombre = int(correspondance.group("n"))
    return nombre if nombre > 0 else None


@dataclass(slots=True)
class LigneAffichee:
    """Ligne de la liste de courses telle qu'affichée (calculée ou manuelle)."""

    uid: str
    libelle: str
    description: str | None
    fait: bool
    calculee: bool
    ligne: LigneCourses | None = None


@dataclass(slots=True)
class ResultatAjout:
    """Résultat de l'ajout d'un plat au menu."""

    plat: PlatMenu
    recette: Recipe | None
    candidats: list[Correspondance] = field(default_factory=list)
    ambigu: bool = False


class Planificateur:
    """Menu de la semaine d'une entrée de configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinateur: CookbookCoordinator,
        stockage: StockagePlanificateur,
    ) -> None:
        self.hass = hass
        self.coordinateur = coordinateur
        self.stockage = stockage
        self._ecouteurs: list[Callable[[], None]] = []

    # --- Abonnements -----------------------------------------------------------------

    @callback
    def async_ecouter(self, rappel: Callable[[], None]) -> CALLBACK_TYPE:
        """Appelle `rappel` à chaque changement. Renvoie la fonction de désabonnement."""
        self._ecouteurs.append(rappel)

        @callback
        def desabonner() -> None:
            self._ecouteurs.remove(rappel)

        return desabonner

    @callback
    def _signaler_changement(self) -> None:
        self.stockage.planifier_sauvegarde()
        for rappel in list(self._ecouteurs):
            rappel()

    # --- Lecture ---------------------------------------------------------------------

    @property
    def recettes(self) -> dict[str, Recipe]:
        """Recettes proposables (catégories exclues retirées)."""
        return self.coordinateur.data.recipes if self.coordinateur.data else {}

    @property
    def couverts_par_defaut(self) -> int:
        return int(self.coordinateur.config_entry.options.get(CONF_SERVINGS, DEFAULT_SERVINGS))

    @property
    def menu(self) -> list[PlatMenu]:
        return self.stockage.donnees.menu

    def recette_du_plat(self, plat: PlatMenu) -> Recipe | None:
        """Recette liée au plat, si elle existe encore (y compris dans une catégorie exclue)."""
        if plat.recipe_id is None or self.coordinateur.data is None:  # pragma: no cover - données absentes
            return None
        index = self.coordinateur.data
        return index.recipes.get(plat.recipe_id) or index.excluded.get(plat.recipe_id)

    def chercher_recettes(self, requete: str, limite: int = 5) -> list[Correspondance]:
        return chercher(requete, list(self.recettes.values()), limite)

    def _plat(self, uid: str) -> PlatMenu:
        for plat in self.menu:
            if plat.uid == uid:
                return plat
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="item_not_found", translation_placeholders={"uid": uid}
        )

    # --- Écriture --------------------------------------------------------------------

    def _position_chronologique(self, jour: date | None) -> int:
        """Index d'insertion : après les plats du même jour ou d'avant, les plats sans date en fin."""
        if jour is None:
            return len(self.menu)
        for index, plat in enumerate(self.menu):
            if plat.day is None or plat.day > jour:
                return index
        return len(self.menu)

    @callback
    def async_ajouter_plat(
        self,
        texte: str,
        *,
        jour: date | None = None,
        couverts: int | None = None,
        recipe_id: str | None = None,
        fait: bool = False,
    ) -> ResultatAjout:
        """Ajoute un plat. Le texte est rapproché d'une recette sauf si `recipe_id` est donné."""
        texte = texte.strip()
        if not texte and recipe_id is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="empty_dish")
        candidats: list[Correspondance] = []
        if recipe_id is not None:
            recette = self.recettes.get(recipe_id)
            if recette is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="recipe_not_found",
                    translation_placeholders={"recipe": recipe_id},
                )
        else:
            recette, candidats = lien_automatique(texte, list(self.recettes.values()))
        plat = PlatMenu(
            uid=uuid4().hex,
            summary=recette.name if recette else texte,
            servings=couverts or self.couverts_par_defaut,
            recipe_id=recette.id if recette else None,
            day=jour,
            done=fait,
        )
        self.menu.insert(self._position_chronologique(jour), plat)
        self._signaler_changement()
        return ResultatAjout(plat=plat, recette=recette, candidats=candidats, ambigu=est_ambigu(candidats))

    @callback
    def async_modifier_plat(
        self,
        uid: str,
        *,
        texte: str | None = None,
        jour: date | object | None = INCHANGE,
        couverts: int | None = None,
        fait: bool | None = None,
    ) -> PlatMenu:
        """Modifie un plat. Un nouveau texte est de nouveau rapproché d'une recette."""
        plat = self._plat(uid)
        if texte is not None and texte.strip() and texte.strip() != plat.summary:
            recette, _ = lien_automatique(texte, list(self.recettes.values()))
            plat.summary = recette.name if recette else texte.strip()
            plat.recipe_id = recette.id if recette else None
        if jour is not INCHANGE:
            plat.day = jour  # type: ignore[assignment]
        if couverts is not None and couverts > 0:
            plat.servings = couverts
        if fait is not None:
            plat.done = fait
        self._signaler_changement()
        return plat

    @callback
    def async_supprimer_plats(self, uids: list[str]) -> None:
        """Retire des plats du menu."""
        for uid in uids:
            self._plat(uid)
        self.stockage.donnees.menu = [p for p in self.menu if p.uid not in set(uids)]
        self._signaler_changement()

    @callback
    def async_deplacer_plat(self, uid: str, uid_precedent: str | None) -> None:
        """Place le plat `uid` juste après `uid_precedent` (en tête si None)."""
        plat = self._plat(uid)
        if uid_precedent is not None:
            self._plat(uid_precedent)
        self.menu.remove(plat)
        index = (
            0
            if uid_precedent is None
            else next(i for i, p in enumerate(self.menu) if p.uid == uid_precedent) + 1
        )
        self.menu.insert(index, plat)
        self._signaler_changement()

    # --- Liste de courses -----------------------------------------------------------

    def _contributions(self) -> list[Contribution]:
        contributions = []
        for plat in self.menu:
            recette = self.recette_du_plat(plat)
            if plat.done or recette is None:
                continue
            contributions.append(
                Contribution(
                    recette=recette.name,
                    couverts=plat.servings,
                    facteur=plat.servings / recette.servings,
                    lignes=recette.ingredients,
                )
            )
        return contributions

    def placard(self) -> set[str]:
        """Clés des produits du placard (complété par la story 2.3)."""
        return set()

    def liste_de_courses(self) -> list[LigneAffichee]:
        """Lignes calculées (par rayon) puis lignes manuelles, avec l'état de cochage appliqué."""
        lignes, _ = calculer(self._contributions(), self.placard())
        etats = self.stockage.donnees.etat_courses
        affichees: list[LigneAffichee] = []
        for ligne in lignes:
            etat = etats.get(ligne.cle, {})
            ajout = augmentation(etat.get("mesure", {}), ligne.mesure()) if etat else {}
            if etat.get("masque") and not ajout:
                continue
            libelle = ligne.libelle
            fait = bool(etat.get("fait")) and not ajout
            if ajout:
                libelle = f"{libelle} +{formater_quantites(ajout)}"
            affichees.append(
                LigneAffichee(
                    uid=f"{PREFIXE_PRODUIT}{ligne.cle}",
                    libelle=libelle,
                    description=ligne.description,
                    fait=fait,
                    calculee=True,
                    ligne=ligne,
                )
            )
        # Oubli des états de produits qui ne sont plus dans la liste (la semaine suivante repart à zéro).
        # Jamais pendant une panne de Nextcloud : les recettes absentes videraient tous les cochages.
        if self.coordinateur.last_update_success and self.coordinateur.data is not None:
            presentes = {ligne.cle for ligne in lignes}
            for cle in [c for c in etats if c not in presentes]:
                del etats[cle]
        for manuelle in self.stockage.donnees.courses_manuelles:
            affichees.append(
                LigneAffichee(
                    uid=manuelle["uid"],
                    libelle=manuelle["summary"],
                    description=manuelle.get("description"),
                    fait=bool(manuelle.get("done")),
                    calculee=False,
                )
            )
        return affichees

    def _ligne_affichee(self, uid: str) -> LigneAffichee:
        for ligne in self.liste_de_courses():
            if ligne.uid == uid:
                return ligne
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="item_not_found", translation_placeholders={"uid": uid}
        )

    @callback
    def async_ajouter_course(self, texte: str, description: str | None = None, fait: bool = False) -> str:
        """Ajoute une ligne manuelle à la liste de courses. Renvoie son uid."""
        texte = texte.strip()
        if not texte:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="empty_dish")
        uid = uuid4().hex
        self.stockage.donnees.courses_manuelles.append(
            {"uid": uid, "summary": texte, "description": description, "done": fait}
        )
        self._signaler_changement()
        return uid

    @callback
    def async_modifier_course(
        self, uid: str, *, texte: str | None, description: str | None, fait: bool
    ) -> None:
        """Modifie une ligne. Pour une ligne calculée, seul le cochage est modifiable."""
        ligne = self._ligne_affichee(uid)
        if ligne.calculee:
            if texte is not None and texte != ligne.libelle:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="computed_item_readonly"
                )
            assert ligne.ligne is not None
            self.stockage.donnees.etat_courses[ligne.ligne.cle] = {
                "fait": fait,
                "mesure": ligne.ligne.mesure(),
            }
        else:
            manuelle = next(m for m in self.stockage.donnees.courses_manuelles if m["uid"] == uid)
            if texte is not None and texte.strip():
                manuelle["summary"] = texte.strip()
            manuelle["description"] = description
            manuelle["done"] = fait
        self._signaler_changement()

    @callback
    def async_supprimer_courses(self, uids: list[str]) -> None:
        """Supprime des lignes. Une ligne calculée est masquée tant que sa quantité n'augmente pas."""
        lignes = [self._ligne_affichee(uid) for uid in uids]
        donnees = self.stockage.donnees
        for ligne in lignes:
            if ligne.calculee:
                assert ligne.ligne is not None
                donnees.etat_courses[ligne.ligne.cle] = {"masque": True, "mesure": ligne.ligne.mesure()}
        manuelles = {ligne.uid for ligne in lignes if not ligne.calculee}
        donnees.courses_manuelles = [m for m in donnees.courses_manuelles if m["uid"] not in manuelles]
        self._signaler_changement()
