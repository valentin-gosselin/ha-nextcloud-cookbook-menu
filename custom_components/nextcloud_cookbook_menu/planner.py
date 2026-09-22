"""Planificateur : source de vérité du menu (et, ensuite, des courses et du placard).

Les entités todo, les actions de service et les outils vocaux passent tous par ici :
aucune logique métier n'est dupliquée ailleurs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .api import Recipe
from .const import (
    CONF_HISTORY_MONTHS,
    CONF_PANTRY,
    CONF_SERVINGS,
    DEFAULT_HISTORY_MONTHS,
    DEFAULT_SERVINGS,
    DOMAIN,
)
from .ingredients import frigo
from .ingredients.aisles import Rayon, rayon
from .ingredients.catalogue_placard import est_produit_de_placard, propositions
from .ingredients.frigo import manque
from .ingredients.normalize import cle, sans_accents
from .ingredients.pantry import PLACARD_PAR_DEFAUT, est_au_placard
from .ingredients.shopping import (
    Contribution,
    LigneCourses,
    arrondir,
    calculer,
    formater_quantites,
)
from .libelles import libelles
from .matching import Correspondance, chercher, est_ambigu, lien_automatique, score
from .store import PlatMenu, StockagePlanificateur

if TYPE_CHECKING:
    from .coordinator import CookbookCoordinator

# Valeur sentinelle : « ne pas modifier ce champ » (None a un sens pour la date).
INCHANGE: Final = object()

PREFIXE_PRODUIT: Final = "produit:"
PREFIXE_RESERVE: Final = "reserve:"
# Score minimal quand on accepte la meilleure recette malgré une ambiguïté.
SEUIL_MEILLEURE: Final = 0.5

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


JOURS_SELECTION: Final = (
    "sans_date", "aujourd_hui", "demain",
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
)  # fmt: skip


@dataclass(slots=True)
class Selection:
    """Choix en cours dans les entités de contrôle (non persisté)."""

    recette: str | None = None
    jour: str = "sans_date"
    couverts: int | None = None


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
        self.selection = Selection()

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

    def plat_par_nom(self, texte: str) -> PlatMenu:
        """Plat du menu le plus proche du texte (pour « retire le carry du menu »)."""
        candidats = sorted(((score(texte, p.summary), p) for p in self.menu), key=lambda c: -c[0])
        if not candidats or candidats[0][0] < SEUIL_MEILLEURE:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="dish_not_in_menu",
                translation_placeholders={"dish": texte},
            )
        return candidats[0][1]

    def choix_recettes(self) -> dict[str, str]:
        """Libellé affiché -> identifiant, triés sans tenir compte des accents. Homonymes précisés."""
        recettes = sorted(self.recettes.values(), key=lambda r: sans_accents(r.name))
        noms = [r.name for r in recettes]
        choix: dict[str, str] = {}
        for recette in recettes:
            libelle = recette.name
            if noms.count(recette.name) > 1:
                libelle = f"{recette.name} ({recette.category or recette.id})"
            choix[libelle] = recette.id
        return choix

    @callback
    def async_modifier_selection(self, **valeurs: Any) -> None:
        """Change la sélection en cours et prévient les entités (rien à sauvegarder)."""
        for champ, valeur in valeurs.items():
            setattr(self.selection, champ, valeur)
        for rappel in list(self._ecouteurs):
            rappel()

    @callback
    def async_ajouter_selection(self, aujourdhui: date) -> dict[str, Any]:
        """Ajoute au menu la recette choisie dans les entités, puis vide le choix de recette."""
        choix = self.choix_recettes()
        if self.selection.recette not in choix:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_recipe_selected")
        jour: date | None = None
        if self.selection.jour == "aujourd_hui":
            jour = aujourdhui
        elif self.selection.jour == "demain":
            jour = aujourdhui + timedelta(days=1)
        elif self.selection.jour in JOURS_SELECTION[3:]:
            index = JOURS_SELECTION.index(self.selection.jour) - 3
            jour = aujourdhui + timedelta(days=(index - aujourdhui.weekday()) % 7)
        bilan = self.async_ajouter_au_menu(
            self.selection.recette,
            jour=jour,
            couverts=self.selection.couverts,
            recipe_id=choix[self.selection.recette],
        )
        self.async_modifier_selection(recette=None)
        return bilan

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
        choisir_meilleure: bool = False,
    ) -> ResultatAjout:
        """Ajoute un plat. Le texte est rapproché d'une recette sauf si `recipe_id` est donné.

        `choisir_meilleure` (voix, actions) : prend la meilleure recette même si le choix est
        ambigu, pourvu qu'elle ressemble assez ; l'UI, elle, ne lie que les correspondances nettes.
        """
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
            if recette is None and choisir_meilleure and candidats and candidats[0].score >= SEUIL_MEILLEURE:
                recette = candidats[0].recette
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
    def async_ajouter_au_menu(
        self,
        texte: str,
        *,
        jour: date | None = None,
        couverts: int | None = None,
        recipe_id: str | None = None,
    ) -> dict[str, Any]:
        """Ajout « intelligent » (actions, voix, LLM) : meilleure recette, et bilan des courses."""
        avant = {ligne.uid: ligne.libelle for ligne in self.liste_de_courses()}
        resultat = self.async_ajouter_plat(
            texte, jour=jour, couverts=couverts, recipe_id=recipe_id, choisir_meilleure=True
        )
        modifiees = [ligne.libelle for ligne in self.liste_de_courses() if avant.get(ligne.uid) != ligne.libelle]
        plat = resultat.plat
        return {
            "dish": plat.summary,
            "recipe_id": plat.recipe_id,
            "linked": resultat.recette is not None,
            "ambiguous": resultat.ambigu,
            "day": plat.day.isoformat() if plat.day else None,
            "servings": plat.servings,
            "uid": plat.uid,
            "alternatives": [
                c.recette.name
                for c in resultat.candidats
                if resultat.recette is None or c.recette.id != resultat.recette.id
            ][:3],
            "shopping_items_changed": modifiees,
        }

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
        if fait is not None and fait != plat.done:
            plat.done = fait
            if fait:
                self.async_consommer()
            elif plat.consumed and (plat.day is None or plat.day >= self._aujourdhui()):
                # Décoché par erreur : sa part revient au frigo.
                if (contribution := self._contribution(plat)) is not None:
                    self._appliquer_consommation(contribution, retirer=False)
                plat.consumed = False
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
        index = 0 if uid_precedent is None else next(i for i, p in enumerate(self.menu) if p.uid == uid_precedent) + 1
        self.menu.insert(index, plat)
        self._signaler_changement()

    @callback
    def async_nouvelle_semaine(self, aujourdhui: date) -> list[dict[str, Any]]:
        """Archive les plats cuisinés ou passés et garde les plats à venir.

        Un plat coché, ou prévu avant aujourd'hui, entre dans l'historique (sa part est d'abord
        retirée du frigo). Un plat à venir ou sans date et non cuisiné reste au menu. L'historique
        plus ancien que la durée de conservation est purgé.
        """
        self.async_consommer(aujourdhui)
        donnees = self.stockage.donnees
        archives: list[dict[str, Any]] = []
        restants: list[PlatMenu] = []
        for plat in self.menu:
            if plat.done or (plat.day is not None and plat.day < aujourdhui):
                archives.append(
                    {
                        "day": (plat.day or aujourdhui).isoformat(),
                        "recipe_id": plat.recipe_id,
                        "summary": plat.summary,
                        "servings": plat.servings,
                    }
                )
            else:
                restants.append(plat)
        donnees.historique.extend(archives)
        limite = (aujourdhui - timedelta(days=30 * self.conservation_mois)).isoformat()
        donnees.historique = [p for p in donnees.historique if (p.get("day") or "") >= limite]
        donnees.menu = restants
        self._signaler_changement()
        return archives

    @property
    def conservation_mois(self) -> int:
        return int(self.coordinateur.config_entry.options.get(CONF_HISTORY_MONTHS, DEFAULT_HISTORY_MONTHS))

    def historique(self, filtre: str | None = None, limite: int = 20) -> list[dict[str, Any]]:
        """Plats archivés, du plus récent au plus ancien, éventuellement filtrés par nom."""
        plats = sorted(self.stockage.donnees.historique, key=lambda p: p.get("day") or "", reverse=True)
        if filtre:
            plats = [p for p in plats if score(filtre, p.get("summary", "")) >= SEUIL_MEILLEURE]
        return plats[:limite]

    # --- Liste de courses et réserve ------------------------------------------------

    def _contribution(self, plat: PlatMenu) -> Contribution | None:
        recette = self.recette_du_plat(plat)
        if recette is None:
            return None
        return Contribution(
            recette=recette.name,
            couverts=plat.servings,
            facteur=plat.servings / recette.servings,
            lignes=recette.ingredients,
        )

    def _contributions(self, aujourdhui: date) -> list[Contribution]:
        """Plats encore à cuisiner : ni cochés, ni consommés, ni passés."""
        contributions = []
        for plat in self.menu:
            if plat.done or plat.consumed or (plat.day is not None and plat.day < aujourdhui):
                continue
            if (contribution := self._contribution(plat)) is not None:
                contributions.append(contribution)
        return contributions

    def produits_placard(self) -> dict[str, str]:
        """Placard : produits des options (sauf ceux sortis) et produits rangés à la main, par clé."""
        donnees = self.stockage.donnees
        options = self.coordinateur.config_entry.options
        produits = {
            c: nom
            for nom in options.get(CONF_PANTRY, PLACARD_PAR_DEFAUT)
            if (c := cle(nom)) and c not in donnees.placard_retires
        }
        for c, nom in donnees.placard_ajouts.items():
            produits.setdefault(c, nom)
        return produits

    def placard(self) -> set[str]:
        """Clés des produits du placard."""
        return set(self.produits_placard())

    def _ranger_au_placard(self, cle_produit: str, nom: str, *, present: bool) -> None:
        """Le produit rejoint le placard (présent ou à racheter) et quitte le frigo et la maison."""
        donnees = self.stockage.donnees
        if cle_produit in donnees.placard_retires:
            donnees.placard_retires.remove(cle_produit)
        if not est_au_placard(cle_produit, self.placard()):
            donnees.placard_ajouts[cle_produit] = nom
        donnees.frigo.pop(cle_produit, None)
        donnees.maison.pop(cle_produit, None)
        if present:
            donnees.placard_epuise.pop(cle_produit, None)
        else:
            donnees.placard_epuise[cle_produit] = nom

    @staticmethod
    def _aujourdhui() -> date:
        return dt_util.now().date()

    def _besoins(self, aujourdhui: date) -> dict[str, LigneCourses]:
        donnees = self.stockage.donnees
        lignes, _ = calculer(self._contributions(aujourdhui), self.placard(), donnees.placard_epuise)
        return {ligne.cle: ligne for ligne in lignes}

    def liste_de_courses(self) -> list[LigneAffichee]:
        """Produits du menu (moins le frigo), produits du placard et de la maison qui manquent."""
        textes = libelles(self.hass)
        donnees = self.stockage.donnees
        affichees: list[tuple[Rayon, str, LigneAffichee]] = []
        for ligne in self._besoins(self._aujourdhui()).values():
            sources = [textes["pour"].format(recette=r, n=n) for r, n in ligne.sources.items()]
            stock = donnees.frigo.get(ligne.cle, {}).get("quantites", {})
            if ligne.cle in donnees.placard_epuise:
                libelle, fait = ligne.libelle, False
                sources.append(textes["placard_epuise"])
            elif ligne.quantites:
                reste = manque(ligne.quantites, stock)
                fait = not reste
                libelle = f"{ligne.nom} ({formater_quantites(reste)})" if reste else ligne.libelle
                if stock:
                    sources.append(textes["au_frigo"].format(quantite=formater_quantites(stock)))
            else:
                libelle, fait = ligne.nom, ligne.cle in donnees.frigo
            affichees.append(
                (
                    ligne.rayon,
                    sans_accents(ligne.nom),
                    LigneAffichee(
                        uid=f"{PREFIXE_PRODUIT}{ligne.cle}",
                        libelle=libelle,
                        description=", ".join(sources),
                        fait=fait,
                        calculee=True,
                        ligne=ligne,
                    ),
                )
            )
        deja = {f"{PREFIXE_PRODUIT}{c}" for c in donnees.placard_epuise} | {a.uid for _, _, a in affichees}
        for cle_produit, nom in donnees.placard_epuise.items():
            if f"{PREFIXE_PRODUIT}{cle_produit}" in {a.uid for _, _, a in affichees}:
                continue
            affichees.append(
                (
                    rayon(cle_produit),
                    sans_accents(nom),
                    LigneAffichee(
                        uid=f"{PREFIXE_RESERVE}{cle_produit}",
                        libelle=nom,
                        description=textes["placard_epuise"],
                        fait=False,
                        calculee=False,
                    ),
                )
            )
        for cle_produit, produit in donnees.maison.items():
            if produit.get("present") or f"{PREFIXE_PRODUIT}{cle_produit}" in deja:
                continue
            affichees.append(
                (
                    rayon(cle_produit),
                    sans_accents(produit["nom"]),
                    LigneAffichee(
                        uid=f"{PREFIXE_RESERVE}{cle_produit}",
                        libelle=produit["nom"],
                        description=produit.get("description"),
                        fait=False,
                        calculee=False,
                    ),
                )
            )
        return [a for _, _, a in sorted(affichees, key=lambda x: (x[0], x[1]))]

    def _ligne_affichee(self, uid: str) -> LigneAffichee:
        for ligne in self.liste_de_courses():
            if ligne.uid == uid:
                return ligne
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="item_not_found", translation_placeholders={"uid": uid}
        )

    @callback
    def async_ajouter_course(self, texte: str, description: str | None = None, fait: bool = False) -> str:
        """Ajout à la main, ou « il n'y en a plus » : le produit rejoint les courses.

        Produit du placard (options, rangé à la main, ou reconnu par l'index des produits qui se
        gardent) : signalé manquant. Produit au frigo : le frigo est vidé de ce produit. Autre
        produit (papier toilette, poêle) : produit « maison » manquant, qui rejoindra la réserve
        une fois acheté.
        """
        texte = texte.strip()
        if not texte:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="empty_dish")
        donnees = self.stockage.donnees
        cle_produit = cle(texte)
        if est_au_placard(cle_produit, self.placard()) or est_produit_de_placard(cle_produit):
            self._ranger_au_placard(cle_produit, texte, present=fait)
            self._signaler_changement()
        else:
            donnees.frigo.pop(cle_produit, None)
            if cle_produit not in self._besoins(self._aujourdhui()) or fait:
                existant = donnees.maison.get(cle_produit, {})
                donnees.maison[cle_produit] = {
                    "nom": existant.get("nom") or texte,
                    "present": fait,
                    "description": description if description is not None else existant.get("description"),
                }
            self._signaler_changement()
        prefixe = PREFIXE_PRODUIT if cle_produit in self._besoins(self._aujourdhui()) else PREFIXE_RESERVE
        return f"{prefixe}{cle_produit}"

    @callback
    def async_modifier_course(self, uid: str, *, texte: str | None, description: str | None, fait: bool) -> None:
        """Cocher, c'est acheter : le produit rejoint le frigo, le placard ou la maison."""
        ligne = self._ligne_affichee(uid)
        donnees = self.stockage.donnees
        if ligne.calculee:
            assert ligne.ligne is not None
            if texte is not None and texte != ligne.libelle:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="computed_item_readonly")
            produit = ligne.ligne
            if produit.cle in donnees.placard_epuise:
                if fait:
                    del donnees.placard_epuise[produit.cle]
            elif fait and not ligne.fait:
                self._acheter(produit)
            elif not fait and ligne.fait:
                # Décoché : l'achat est annulé. Un produit rangé au placard n'a plus de ligne ici.
                if produit.quantites:
                    frigo.retirer(donnees.frigo, produit.cle, produit.mesure())
                else:
                    donnees.frigo.pop(produit.cle, None)
        else:
            cle_produit = uid.removeprefix(PREFIXE_RESERVE)
            if cle_produit in donnees.placard_epuise:
                if fait:
                    del donnees.placard_epuise[cle_produit]
            else:
                produit_maison = donnees.maison[cle_produit]
                if texte is not None and texte.strip():
                    produit_maison["nom"] = texte.strip()
                produit_maison["description"] = description
                produit_maison["present"] = fait
        self._signaler_changement()

    def _acheter(self, produit: LigneCourses) -> None:
        donnees = self.stockage.donnees
        if est_produit_de_placard(produit.cle):
            # Levure, miel, pâtes : ça se garde, ça rejoint le placard et non le frigo.
            self._ranger_au_placard(produit.cle, produit.nom, present=True)
            return
        stock = donnees.frigo.get(produit.cle, {}).get("quantites", {})
        # On achète des quantités arrondies (un citron entier, pas un demi).
        achat = (
            {m: arrondir(m, v) for m, v in manque(produit.quantites, stock).items()}
            if produit.quantites
            else {"pièce": 1}
        )
        frigo.ajouter(donnees.frigo, produit.cle, produit.nom, achat, produit.rayon, self._aujourdhui())

    @callback
    def async_supprimer_courses(self, uids: list[str]) -> None:
        """Supprimer une ligne du menu vaut « j'en ai déjà » ; une ligne de réserve sort de la réserve."""
        lignes = [self._ligne_affichee(uid) for uid in uids]
        donnees = self.stockage.donnees
        for ligne in lignes:
            if ligne.calculee:
                assert ligne.ligne is not None
                if ligne.ligne.cle in donnees.placard_epuise:
                    del donnees.placard_epuise[ligne.ligne.cle]
                elif not ligne.fait:
                    self._acheter(ligne.ligne)
            else:
                cle_produit = ligne.uid.removeprefix(PREFIXE_RESERVE)
                donnees.placard_epuise.pop(cle_produit, None)
                donnees.maison.pop(cle_produit, None)
        self._signaler_changement()

    @callback
    def async_consommer(self, aujourdhui: date | None = None) -> None:
        """Retire du frigo la part des plats cuisinés ou passés, puis les produits expirés."""
        aujourdhui = aujourdhui or self._aujourdhui()
        donnees = self.stockage.donnees
        modifie = bool(frigo.expirer(donnees.frigo, aujourdhui))
        for plat in self.menu:
            fini = plat.done or (plat.day is not None and plat.day < aujourdhui)
            if fini and not plat.consumed and (contribution := self._contribution(plat)) is not None:
                self._appliquer_consommation(contribution, retirer=True)
                plat.consumed = True
                modifie = True
        if modifie:
            self._signaler_changement()

    def _appliquer_consommation(self, contribution: Contribution, *, retirer: bool) -> None:
        donnees = self.stockage.donnees
        lignes, _ = calculer([contribution], self.placard(), donnees.placard_epuise)
        for ligne in lignes:
            if not ligne.quantites:
                continue
            if retirer:
                frigo.retirer(donnees.frigo, ligne.cle, ligne.quantites)
            elif ligne.cle in donnees.frigo:
                frigo.ajouter(donnees.frigo, ligne.cle, ligne.nom, ligne.quantites, ligne.rayon, self._aujourdhui())

    # --- Réserve (carte et voix) ----------------------------------------------------

    def reserve(self) -> dict[str, Any]:
        """Placard, frigo et maison, pour la carte « Réserve »."""
        donnees = self.stockage.donnees
        aujourdhui = self._aujourdhui()
        placard = [
            {"key": c, "name": nom, "missing": c in donnees.placard_epuise}
            for c, nom in self.produits_placard().items()
        ]
        noms_options = {p["key"] for p in placard}
        placard.extend(
            {"key": c, "name": nom, "missing": True}
            for c, nom in donnees.placard_epuise.items()
            if c not in noms_options
        )
        return {
            "pantry_checked": donnees.placard_verifie,
            "pantry": sorted(placard, key=lambda p: sans_accents(p["name"])),
            "fridge": sorted(
                (
                    {
                        "key": c,
                        "name": e["nom"],
                        "quantity": formater_quantites(e["quantites"]),
                        "days_left": (date.fromisoformat(e["expire"]) - aujourdhui).days if e.get("expire") else None,
                    }
                    for c, e in donnees.frigo.items()
                ),
                key=lambda p: sans_accents(p["name"]),
            ),
            "home": sorted(
                (
                    {
                        "key": c,
                        "name": m["nom"],
                        "present": bool(m.get("present")),
                        "description": m.get("description"),
                    }
                    for c, m in donnees.maison.items()
                ),
                key=lambda p: sans_accents(p["name"]),
            ),
        }

    @callback
    def async_reserve_present(self, cle_produit: str) -> None:
        """« J'en ai » : le produit n'est plus à acheter."""
        donnees = self.stockage.donnees
        donnees.placard_epuise.pop(cle_produit, None)
        if cle_produit in donnees.maison:
            donnees.maison[cle_produit]["present"] = True
        self._signaler_changement()

    @callback
    def async_reserve_manquant(self, cle_produit: str) -> None:
        """« Il n'y en a plus » depuis la carte, par clé de produit."""
        donnees = self.stockage.donnees
        produits_placard = self.produits_placard()
        if cle_produit in donnees.maison:
            donnees.maison[cle_produit]["present"] = False
        elif cle_produit in produits_placard:
            donnees.placard_epuise[cle_produit] = produits_placard[cle_produit]
        elif cle_produit in donnees.frigo:
            nom = donnees.frigo.pop(cle_produit)["nom"]
            if cle_produit not in self._besoins(self._aujourdhui()):
                donnees.maison[cle_produit] = {"nom": nom, "present": False, "description": None}
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_not_found",
                translation_placeholders={"uid": cle_produit},
            )
        self._signaler_changement()

    @callback
    def async_reserve_retirer(self, cle_produit: str) -> None:
        """Sortir un produit de la réserve (frigo, maison ou placard)."""
        donnees = self.stockage.donnees
        donnees.frigo.pop(cle_produit, None)
        donnees.maison.pop(cle_produit, None)
        donnees.placard_epuise.pop(cle_produit, None)
        if donnees.placard_ajouts.pop(cle_produit, None) is None and cle_produit in self.placard():
            donnees.placard_retires.append(cle_produit)
        self._signaler_changement()

    def propositions_placard(self) -> list[dict[str, str]]:
        """Produits de l'index qui ne sont pas encore au placard, pour la liste de la carte."""
        placard = self.placard()
        return sorted(
            ({"key": c, "name": nom} for c, nom in propositions().items() if not est_au_placard(c, placard)),
            key=lambda p: sans_accents(p["name"]),
        )

    @callback
    def async_reserve_au_placard(self, *, noms: list[str] | None = None, cle_produit: str | None = None) -> None:
        """Ranger au placard des produits choisis ou saisis dans la carte, ou un produit de la maison."""
        donnees = self.stockage.donnees
        if cle_produit is not None:
            if cle_produit not in donnees.maison:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="item_not_found",
                    translation_placeholders={"uid": cle_produit},
                )
            produit = donnees.maison[cle_produit]
            self._ranger_au_placard(cle_produit, produit["nom"], present=bool(produit.get("present")))
        else:
            produits: dict[str, str] = {}
            for nom in (n.strip() for n in noms or []):
                if c := cle(nom):
                    produits.setdefault(c, nom)
            if not produits:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="empty_dish")
            for c, nom in produits.items():
                self._ranger_au_placard(c, nom, present=True)
        self._signaler_changement()

    @callback
    def async_valider_placard(self, manquants: list[str]) -> None:
        """Première vérification du placard : seuls les produits décochés sont à racheter."""
        donnees = self.stockage.donnees
        noms = self.produits_placard()
        for cle_produit in manquants:
            if cle_produit in noms:
                donnees.placard_epuise[cle_produit] = noms[cle_produit]
        donnees.placard_verifie = True
        self._signaler_changement()
