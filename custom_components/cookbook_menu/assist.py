"""Voix avec l'agent de conversation par défaut (story 3.1).

Les phrases sont enregistrées comme déclencheurs de phrases, le mécanisme des automatisations
« Phrase » : il accepte des jokers ({demande}) que l'on analyse ensuite librement. Les ajouts et
cochages de lignes de courses restent gérés par les intents natifs de Home Assistant.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .jours import lire_jour
from .voix import analyser_demande, detecter_langue

if TYPE_CHECKING:
    from hassil.recognize import RecognizeResult

    from .planner import Planificateur

# Groupes de verbes, pour garder les motifs lisibles.
_AJOUTER = (
    "ajoute|ajoutes|ajouter|rajoute|rajoutes|rajouter|mets|met|mettre|note|inscris|programme"
    "|planifie|prévois|prevois|prépare|prepare"
)
_AJOUTER_INFINITIF = "ajouter|mettre|prévoir|prevoir|noter|programmer|planifier"
_ON_MANGE = (
    "on mange|on va manger|on mangera|on se fait|on fait|on fera|on cuisine|on prend"
    "|je fais|je cuisine|je prépare|je prepare"
)
_WE_HAVE = (
    "we're having|we are having|we'll have|we will have|let's have|lets have"
    "|i'm making|i am making|i'll cook|we're cooking|we are cooking"
)
_MANGE_PASSE = "mangé|mange|fait|cuisiné|cuisine|préparé|prepare"
_RETIRER = "retire|retirer|enlève|enleve|enlever|supprime|supprimer|annule|annuler|vire|efface"
_MENU = "(au|dans le) menu [de la semaine]"
_THE_MENU = "[the] [weekly] (menu|meal plan)"

PHRASES_AJOUT = [
    # Français
    f"({_AJOUTER}) {{demande}} {_MENU} [{{suite}}]",
    f"({_AJOUTER}) {_MENU} {{demande}}",
    f"{_MENU} {{suite}} ({_AJOUTER}) {{demande}}",
    f"(je voudrais|j'aimerais|je veux|il faudrait|faudrait) ({_AJOUTER_INFINITIF}) {{demande}} {_MENU}"
    " [{suite}]",
    f"(peux-tu|peux tu|tu peux|pourrais-tu|pourrais tu) ({_AJOUTER_INFINITIF}) {{demande}} {_MENU}"
    " [{suite}]",
    f"({_ON_MANGE}) {{demande}}",
    f"pour {{suite}} ({_AJOUTER}|{_ON_MANGE}) {{demande}} [au menu]",
    # English
    f"(add|adds|put|plan|schedule|book) {{demande}} (to|on|in) {_THE_MENU} [{{suite}}]",
    f"(add|put|plan|schedule) (to|on) {_THE_MENU} {{demande}}",
    f"(on|in) {_THE_MENU} {{suite}} (add|put|plan) {{demande}}",
    f"({_WE_HAVE}) {{demande}}",
    f"(can you|could you|please) (add|put|plan|schedule) {{demande}} (to|on) {_THE_MENU} [{{suite}}]",
]
PHRASES_MENU = [
    # Français
    "qu'est-ce qu'on (mange|cuisine|se fait|a prévu|a prevu) [{quand}]",
    "on (mange|cuisine|se fait) quoi [{quand}]",
    "on a prévu quoi [{quand}]",
    "(qu'est-ce qu'il y a|qu'y a-t-il|qu'y a t il) au menu [{quand}]",
    "qu'est-ce qui est prévu [au menu] [{quand}]",
    "(c'est quoi|quel est|donne-moi|donne moi|rappelle-moi|rappelle moi) le menu [{quand}]",
    "(c'est quoi|quel est) le (repas|dîner|diner|déjeuner|dejeuner) [{quand}]",
    "[le] menu [de|du|pour] {quand}",
    # English
    "(what's|what is) for (dinner|lunch|supper|tea) [{quand}]",
    "what are we (eating|having|cooking|making) [{quand}]",
    "what's (on|for) [the] (menu|meal plan) [{quand}]",
    "what's the (menu|meal plan) [{quand}]",
    "what's planned [for] [{quand}]",
    "(tell me|give me|remind me) [about] the (menu|meal plan) [{quand}]",
]
PHRASES_HISTORIQUE = [
    # Français
    "quand (est-ce qu'on a|est-ce que j'ai|avons-nous|avons nous|a-t-on|a t on|on a|j'ai)"
    f" ({_MANGE_PASSE}) {{demande}}",
    "c'est quand la dernière fois (qu'on a|que j'ai) (mangé|fait|cuisiné) {demande}",
    "[ça|ca] fait combien de temps (qu'on n'a pas|qu'on a pas|que je n'ai pas)"
    " (mangé|fait|cuisiné) {demande}",
    "la dernière fois (qu'on a|que j'ai) (mangé|fait|cuisiné) {demande} c'était quand",
    # English
    "when did we (last eat|last have|last cook|last make|eat|have|cook|make) {demande}",
    "when was the last time we (ate|had|cooked|made) {demande}",
    "how long since we (ate|had|cooked|made) {demande}",
]
PHRASES_MANQUE = [
    # Français
    "il (n'y a|y a|n'y avait) plus [de|d'|du|des|le|la|les] {demande}",
    "(y'a|y a) plus [de|d'|du|des] {demande}",
    "(on n'a|on a|nous n'avons|j'ai|je n'ai|il ne reste|il reste) plus [de|d'|du|des|le|la|les] {demande}",
    "(on est|je suis|nous sommes) à court [de|d'|du|des] {demande}",
    "(on manque|je manque|nous manquons) [de|d'|du|des] {demande}",
    "(il faut|faut|il faudrait|faudrait) (racheter|reprendre|rajouter)"
    " [du|de|de la|des|de l'|le|la|les] {demande}",
    "(note|noter|ajoute|ajouter|marque) qu'il n'y a plus [de|d'|du|des] {demande}",
    "(il me faut|il nous faut|j'ai besoin|on a besoin) [du|de|de la|des|de l'] {demande}",
    # English
    "(we're|we are|we ran|we've run|i'm|i am|i ran) out of {demande}",
    "(we have|there's|there is) no more {demande}",
    "(we're|we are) running low on {demande}",
    "we need [some|more] {demande}",
]
PHRASES_RETRAIT = [
    # Français
    f"({_RETIRER}) {{demande}} du menu [de la semaine]",
    f"({_RETIRER}) {{demande}} de la semaine",
    "(je ne veux plus|on ne veut plus|je veux plus) [de|d'|du|des] {demande} (au|dans le) menu",
    "(peux-tu|tu peux|peux tu) (retirer|enlever|supprimer|annuler) {demande} du menu [de la semaine]",
    # English
    f"(remove|delete|cancel|drop) {{demande}} (from|off) {_THE_MENU}",
    f"take {{demande}} (off|out of) {_THE_MENU}",
    "(i don't want|we don't want) {demande} (on|in) [the] menu [anymore]",
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
        "prefixe_jour": "",
        "menu": "{jour} : {plats}.",
        "menu_vide": "Rien de prévu {jour}.",
        "prochain": " Prochain plat : {plat} {jour}.",
        "retrait": "C'est fait, {plat} est retiré du menu.",
        "introuvable": "Je ne trouve pas {plat} dans le menu.",
        "non_configure": "Cookbook Menu n'est pas configuré.",
        "plat_vide": "Quel plat faut-il ajouter au menu ?",
        "manque": "C'est noté, {produit} est dans les courses.",
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
        "jour": " {jour}",
        "prefixe_jour": "on ",
        "menu": "{jour}: {plats}.",
        "menu_vide": "Nothing planned {jour}.",
        "prochain": " Next dish: {plat} {jour}.",
        "retrait": "Done, {plat} was removed from the menu.",
        "introuvable": "I can't find {plat} in the menu.",
        "non_configure": "Cookbook Menu is not configured.",
        "plat_vide": "Which dish should I add to the menu?",
        "manque": "Noted, {produit} is on the shopping list.",
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


def _texte_jour(jour: date, aujourdhui: date, textes: dict, *, dans_phrase: bool = False) -> str:
    """« jeudi », « demain ». Au fil d'une phrase, l'anglais veut « on Thursday » mais « tomorrow »."""
    if jour == aujourdhui:
        return textes["aujourd_hui"]
    if (jour - aujourdhui).days == 1:
        return textes["demain"]
    nom = textes["jours"][jour.weekday()]
    return f"{textes['prefixe_jour']}{nom}" if dans_phrase else nom


def texte_courses(nombre: int, textes: dict) -> str:
    """Bilan des courses à ajouter à la réponse (vide si rien n'a changé)."""
    if nombre == 0:
        return ""
    if nombre == 1:
        return textes["ajout_un_produit"]
    return textes["ajout_courses"].format(n=nombre)


# « on mange quoi demain » ressemble à « on mange des pâtes demain » : c'est une question.
_INTERROGATIF = re.compile(r"^(?:quoi|qu'est-ce|que|quel|quelle|combien|what|which)\b", re.IGNORECASE)


def _valeur(resultat: RecognizeResult, nom: str) -> str:
    entite = resultat.entities.get(nom)
    return str(entite.value).strip() if entite is not None else ""


@callback
def async_enregistrer_phrases(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Enregistre les phrases auprès de l'agent par défaut. Renvoie la fonction de retrait."""
    gestionnaire = get_agent_manager(hass)

    async def ajouter(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = detecter_langue(entree.text, entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        aujourdhui = dt_util.now().date()
        demande = analyser_demande(f"{_valeur(resultat, 'demande')} {_valeur(resultat, 'suite')}", code)
        if _INTERROGATIF.match(demande.plat):
            # « on mange quoi demain » : c'est la question du menu, pas un plat à ajouter.
            return reponse_menu(planificateur, textes, demande.jour)
        if not demande.plat:
            return textes["plat_vide"]
        # analyser_demande ne renvoie que des jours reconnus : lire_jour ne peut pas échouer ici.
        jour = lire_jour(demande.jour, aujourdhui)
        bilan = planificateur.async_ajouter_au_menu(demande.plat, jour=jour, couverts=demande.couverts)
        texte_jour = (
            textes["jour"].format(jour=_texte_jour(jour, aujourdhui, textes, dans_phrase=True))
            if jour
            else ""
        )
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

    def reponse_menu(planificateur: Planificateur, textes: dict, jour_dit: str | None) -> str:
        aujourdhui = dt_util.now().date()
        jour = lire_jour(jour_dit, aujourdhui) or aujourdhui
        texte_jour = _texte_jour(jour, aujourdhui, textes)
        plats = [p.summary for p in planificateur.menu if p.day == jour and not p.done]
        if plats:
            return textes["menu"].format(
                jour=texte_jour[0].upper() + texte_jour[1:], plats=textes["et"].join(plats)
            )
        reponse = textes["menu_vide"].format(jour=_texte_jour(jour, aujourdhui, textes, dans_phrase=True))
        suivants = sorted(
            (p for p in planificateur.menu if p.day and p.day > jour and not p.done), key=lambda p: p.day
        )
        if suivants:
            reponse += textes["prochain"].format(
                plat=suivants[0].summary,
                jour=_texte_jour(suivants[0].day, aujourdhui, textes, dans_phrase=True),
            )
        return reponse

    async def menu(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = detecter_langue(entree.text, entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        return reponse_menu(planificateur, textes, analyser_demande(_valeur(resultat, "quand"), code).jour)

    async def retirer(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = detecter_langue(entree.text, entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        demande = analyser_demande(_valeur(resultat, "demande"), code)
        try:
            plat = planificateur.plat_par_nom(demande.plat)
        except HomeAssistantError:
            return textes["introuvable"].format(plat=demande.plat)
        planificateur.async_supprimer_plats([plat.uid])
        return textes["retrait"].format(plat=plat.summary)

    async def historique(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = detecter_langue(entree.text, entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        demande = analyser_demande(_valeur(resultat, "demande"), code)
        [dernier, *_] = planificateur.historique(demande.plat, 1) or [None]
        if dernier is None:
            return textes["historique_jamais"].format(plat=demande.plat)
        jour = date.fromisoformat(dernier["day"])
        mois = textes["mois"][jour.month - 1]
        texte_date = f"{jour.day} {mois} {jour.year}" if code == "fr" else f"{mois} {jour.day}, {jour.year}"
        return textes["historique"].format(plat=dernier["summary"], date=texte_date)

    async def manque(entree: ConversationInput, resultat: RecognizeResult) -> str:
        code = detecter_langue(entree.text, entree.language)
        textes = _REPONSES[code]
        planificateur = _planificateur(hass)
        if planificateur is None:
            return textes["non_configure"]
        produit = analyser_demande(_valeur(resultat, "demande"), code).plat
        produit = re.sub(r"^(?:d'|l')", "", produit).strip()
        planificateur.async_ajouter_course(produit[:1].upper() + produit[1:])
        return textes["manque"].format(produit=produit)

    retraits = [
        gestionnaire.register_trigger(PHRASES_MANQUE, manque),
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
