"""Voix avec l'agent de conversation par défaut (story 3.1).

Les phrases sont enregistrées comme déclencheurs de phrases, le mécanisme des automatisations
« Phrase » : il accepte des jokers ({demande}) que l'on analyse ensuite librement. Les ajouts et
cochages de lignes de courses restent gérés par les intents natifs de Home Assistant.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .jours import lire_jour
from .voix import analyser_demande, langue

if TYPE_CHECKING:
    from hassil.recognize import RecognizeResult

    from .planner import Planificateur

PHRASES_AJOUT = [
    # Français
    "(ajoute|ajouter|rajoute|mets|met|mettre|prévois|planifie) {demande} au menu [de la semaine] [{suite}]",
    "au menu [de la semaine] {suite} (ajoute|mets|prévois) {demande}",
    # English
    "(add|put|plan) {demande} (to|on) [the] [weekly] menu [{suite}]",
]
PHRASES_MENU = [
    "qu'est-ce qu'on mange [{quand}]",
    "on mange quoi [{quand}]",
    "qu'est-ce qu'il y a au menu [{quand}]",
    "(c'est quoi|quel est) le menu [{quand}]",
    "what's for (dinner|lunch) [{quand}]",
    "what are we eating [{quand}]",
    "what's on the menu [{quand}]",
]
PHRASES_HISTORIQUE = [
    "quand (est-ce qu'on a|avons-nous|a-t-on) (mangé|fait|cuisiné) {demande}",
    "c'est quand la dernière fois qu'on a (mangé|fait) {demande}",
    "when did we (last eat|last have|last cook|eat|have) {demande}",
]
PHRASES_RETRAIT = [
    "(retire|enlève|supprime|annule) {demande} du menu",
    "remove {demande} from [the] menu",
]

_REPONSES = {
    "fr": {
        "ajout": "C'est noté : {plat}{jour}{couverts}.",
        "ajout_courses": " {n} produits ajoutés ou modifiés dans les courses.",
        "ajout_un_produit": " 1 produit ajouté ou modifié dans les courses.",
        "ajout_libre": "C'est noté : {plat}{jour}, sans recette associée.",
        "alternative": " Sinon, il y a aussi {autre}.",
        "couverts": " pour {n}",
        "jour": " {jour}",
        "menu": "{jour} : {plats}.",
        "menu_vide": "Rien de prévu {jour}.",
        "prochain": " Prochain plat : {plat} {jour}.",
        "retrait": "C'est fait, {plat} est retiré du menu.",
        "introuvable": "Je ne trouve pas {plat} dans le menu.",
        "non_configure": "Cookbook Menu n'est pas configuré.",
        "plat_vide": "Quel plat faut-il ajouter au menu ?",
        "historique": "La dernière fois : {plat}, le {date}.",
        "historique_jamais": "Pas de {plat} dans l'historique.",
        "mois": [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ],
        "et": " et ",
        "aujourd_hui": "aujourd'hui",
        "demain": "demain",
        "jours": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    },
    "en": {
        "ajout": "Done: {plat}{jour}{couverts}.",
        "ajout_courses": " {n} shopping items added or updated.",
        "ajout_un_produit": " 1 shopping item added or updated.",
        "ajout_libre": "Done: {plat}{jour}, with no matching recipe.",
        "alternative": " There is also {autre}.",
        "couverts": " for {n}",
        "jour": " on {jour}",
        "menu": "{jour}: {plats}.",
        "menu_vide": "Nothing planned {jour}.",
        "prochain": " Next dish: {plat} on {jour}.",
        "retrait": "Done, {plat} was removed from the menu.",
        "introuvable": "I can't find {plat} in the menu.",
        "non_configure": "Cookbook Menu is not configured.",
        "plat_vide": "Which dish should I add to the menu?",
        "historique": "Last time: {plat}, on {date}.",
        "historique_jamais": "No {plat} in the history.",
        "mois": [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        "et": " and ",
        "aujourd_hui": "today",
        "demain": "tomorrow",
        "jours": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    },
}


def _planificateur(hass: HomeAssistant) -> Planificateur | None:
    for entree in hass.config_entries.async_loaded_entries(DOMAIN):
        return entree.runtime_data.planner
    return None


def _texte_jour(jour: date, aujourdhui: date, textes: dict) -> str:
    if jour == aujourdhui:
        return textes["aujourd_hui"]
    if (jour - aujourdhui).days == 1:
        return textes["demain"]
    return textes["jours"][jour.weekday()]


def texte_courses(nombre: int, textes: dict) -> str:
    """Bilan des courses à ajouter à la réponse (vide si rien n'a changé)."""
    if nombre == 0:
        return ""
    if nombre == 1:
        return textes["ajout_un_produit"]
    return textes["ajout_courses"].format(n=nombre)


def _valeur(resultat: RecognizeResult, nom: str) -> str:
    entite = resultat.entities.get(nom)
    return str(entite.value).strip() if entite is not None else ""


@callback
def async_enregistrer_phrases(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Enregistre les phrases auprès de l'agent par défaut. Renvoie la fonction de retrait."""
    gestionnaire = get_agent_manager(hass)

    async def ajouter(entree: ConversationInput, resultat: RecognizeResult) -> str:
        textes = _REPONSES[langue(entree.language)]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        aujourdhui = dt_util.now().date()
        demande = analyser_demande(
            f"{_valeur(resultat, 'demande')} {_valeur(resultat, 'suite')}", entree.language
        )
        if not demande.plat:
            return textes["plat_vide"]
        # analyser_demande ne renvoie que des jours reconnus : lire_jour ne peut pas échouer ici.
        jour = lire_jour(demande.jour, aujourdhui)
        bilan = planificateur.async_ajouter_au_menu(demande.plat, jour=jour, couverts=demande.couverts)
        texte_jour = textes["jour"].format(jour=_texte_jour(jour, aujourdhui, textes)) if jour else ""
        if not bilan["linked"]:
            return textes["ajout_libre"].format(plat=bilan["dish"], jour=texte_jour)
        reponse = textes["ajout"].format(
            plat=bilan["dish"],
            jour=texte_jour,
            couverts=textes["couverts"].format(n=bilan["servings"]),
        )
        reponse += texte_courses(len(bilan["shopping_items_changed"]), textes)
        if bilan["ambiguous"] and bilan["alternatives"]:
            reponse += textes["alternative"].format(autre=bilan["alternatives"][0])
        return reponse

    async def menu(entree: ConversationInput, resultat: RecognizeResult) -> str:
        textes = _REPONSES[langue(entree.language)]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        aujourdhui = dt_util.now().date()
        demande = analyser_demande(_valeur(resultat, "quand"), entree.language)
        jour = lire_jour(demande.jour, aujourdhui) or aujourdhui
        texte_jour = _texte_jour(jour, aujourdhui, textes)
        plats = [p.summary for p in planificateur.menu if p.day == jour and not p.done]
        if plats:
            return textes["menu"].format(
                jour=texte_jour[0].upper() + texte_jour[1:], plats=textes["et"].join(plats)
            )
        reponse = textes["menu_vide"].format(jour=texte_jour)
        suivants = sorted(
            (p for p in planificateur.menu if p.day and p.day > jour and not p.done), key=lambda p: p.day
        )
        if suivants:
            reponse += textes["prochain"].format(
                plat=suivants[0].summary, jour=_texte_jour(suivants[0].day, aujourdhui, textes)
            )
        return reponse

    async def retirer(entree: ConversationInput, resultat: RecognizeResult) -> str:
        textes = _REPONSES[langue(entree.language)]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        demande = analyser_demande(_valeur(resultat, "demande"), entree.language)
        try:
            plat = planificateur.plat_par_nom(demande.plat)
        except HomeAssistantError:
            return textes["introuvable"].format(plat=demande.plat)
        planificateur.async_supprimer_plats([plat.uid])
        return textes["retrait"].format(plat=plat.summary)

    async def historique(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = langue(entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        demande = analyser_demande(_valeur(resultat, "demande"), entree.language)
        [dernier, *_] = planificateur.historique(demande.plat, 1) or [None]
        if dernier is None:
            return textes["historique_jamais"].format(plat=demande.plat)
        jour = date.fromisoformat(dernier["day"])
        mois = textes["mois"][jour.month - 1]
        texte_date = f"{jour.day} {mois} {jour.year}" if code == "fr" else f"{mois} {jour.day}, {jour.year}"
        return textes["historique"].format(plat=dernier["summary"], date=texte_date)

    retraits = [
        gestionnaire.register_trigger(PHRASES_HISTORIQUE, historique),
        gestionnaire.register_trigger(PHRASES_AJOUT, ajouter),
        gestionnaire.register_trigger(PHRASES_MENU, menu),
        gestionnaire.register_trigger(PHRASES_RETRAIT, retirer),
    ]

    @callback
    def retirer_tout() -> None:
        for retrait in retraits:
            retrait()

    return retirer_tout
