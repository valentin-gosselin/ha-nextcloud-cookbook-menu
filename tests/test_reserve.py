"""Réserve : placard, maison et vérification initiale (story 2.10)."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.cookbook_menu.ingredients.pantry import cles_placard, est_au_placard

from .test_courses import COURSES, cocher, courses
from .test_menu import ajouter


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


async def installer(hass: HomeAssistant, config_entry, **options) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, **options})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def ajouter_course(hass: HomeAssistant, texte: str) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES, "item": texte}, blocking=True
    )


def test_familles_et_cles() -> None:
    placard = cles_placard(["Huile", "Sel", "Sucre", ""])
    assert est_au_placard("huile sesame", placard)
    assert not est_au_placard("sucre glace", placard)
    assert est_au_placard("vinaigre balsamique", cles_placard(["Vinaigre"]))


async def test_couscous_sans_placard(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, pantry=["Huile d'olive", "Épices à couscous", "Harissa", "Sel"])
    await ajouter(hass, "couscous")
    assert not any(libelle.startswith(("Huile", "Épices", "Harissa")) for libelle in await courses(hass))


async def test_il_n_y_a_plus_d_huile(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await ajouter(hass, "carry", description="pour 6")
    assert not any(libelle.startswith("Huile") for libelle in await courses(hass))

    await ajouter_course(hass, "huile")
    ligne = (await courses(hass))["Huile (4 c. à s.)"]
    assert ligne["description"] == "Carry de poulet pour 6, manque au placard"

    await ajouter_course(hass, "Muscade")  # pas utilisée par le menu : ligne seule
    assert (await courses(hass))["Muscade"]["description"] == "manque au placard"

    await cocher(hass, "Huile (4 c. à s.)")
    await cocher(hass, "Muscade")
    lignes = await courses(hass)
    assert "Muscade" not in lignes and not any(libelle.startswith("Huile") for libelle in lignes)
    planificateur = config_entry.runtime_data.planner
    assert planificateur.stockage.donnees.placard_epuise == {}
    assert "huile" not in planificateur.stockage.donnees.frigo


async def test_produits_maison(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await ajouter_course(hass, "Papier toilette")
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": COURSES,
            "item": "Papier toilette",
            "rename": "Papier toilette x12",
            "description": "promo",
        },
        blocking=True,
    )
    ligne = (await courses(hass))["Papier toilette x12"]
    assert (ligne["description"], ligne["status"]) == ("promo", "needs_action")

    await cocher(hass, "Papier toilette x12")
    assert "Papier toilette x12" not in await courses(hass)  # rangé dans la réserve
    planificateur = config_entry.runtime_data.planner
    maison = planificateur.reserve()["home"]
    assert maison == [
        {"key": "papier toilette", "name": "Papier toilette x12", "present": True, "description": "promo"}
    ]

    # « Il n'y en a plus » depuis la carte, puis sortie de la réserve.
    planificateur.async_reserve_manquant("papier toilette")
    assert "Papier toilette x12" in await courses(hass)
    planificateur.async_reserve_present("papier toilette")
    assert "Papier toilette x12" not in await courses(hass)
    planificateur.async_reserve_retirer("papier toilette")
    assert planificateur.reserve()["home"] == []

    await ajouter_course(hass, "Poêle")
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Poêle"}, blocking=True
    )
    assert planificateur.reserve()["home"] == []


async def test_produit_au_frigo_signale_manquant(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry)
    await ajouter(hass, "salade cesar")
    await cocher(hass, "Citron (1)")
    planificateur = config_entry.runtime_data.planner
    assert planificateur.reserve()["fridge"] == [
        {"key": "citron", "name": "Citron", "quantity": "1", "days_left": 7}
    ]
    await ajouter_course(hass, "citron")  # « il n'y a plus de citron » : le frigo se vide
    assert (await courses(hass))["Citron (1)"]["status"] == "needs_action"
    assert planificateur.reserve()["home"] == []

    await cocher(hass, "Citron (1)")
    planificateur.async_reserve_manquant("citron")
    assert (await courses(hass))["Citron (1)"]["status"] == "needs_action"


async def test_verification_initiale_du_placard(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, pantry=["Sel", "Poivre", "Huile"])
    planificateur = config_entry.runtime_data.planner
    reserve = planificateur.reserve()
    assert reserve["pantry_checked"] is False
    assert [p["name"] for p in reserve["pantry"]] == ["Huile", "Poivre", "Sel"]
    assert not any(p["missing"] for p in reserve["pantry"])

    planificateur.async_valider_placard(["poivre", "inconnu"])
    reserve = planificateur.reserve()
    assert reserve["pantry_checked"] is True
    assert [p["name"] for p in reserve["pantry"] if p["missing"]] == ["Poivre"]
    assert "Poivre" in await courses(hass)

    planificateur.async_reserve_manquant("sel")
    await ajouter_course(hass, "Huile de sésame")  # famille « huile », hors options
    assert {p["name"] for p in planificateur.reserve()["pantry"] if p["missing"]} == {
        "Poivre",
        "Sel",
        "Huile de sésame",
    }
    with pytest.raises(ServiceValidationError):
        planificateur.async_reserve_manquant("inconnu")


async def test_websocket_reserve(hass: HomeAssistant, mock_client, config_entry, hass_ws_client) -> None:
    await installer(hass, config_entry, pantry=["Sel", "Poivre"])
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "cookbook_menu/stock/subscribe"})
    assert (await client.receive_json())["success"]
    instantane = (await client.receive_json())["event"]
    assert instantane["pantry_checked"] is False
    assert [p["name"] for p in instantane["pantry"]] == ["Poivre", "Sel"]

    await client.send_json_auto_id(
        {"type": "cookbook_menu/stock/update", "action": "check_pantry", "missing": ["sel"]}
    )
    evenement = await client.receive_json()
    resultat = await client.receive_json()
    messages = {m.get("type"): m for m in (evenement, resultat)}
    assert messages["result"]["success"]
    assert [p["name"] for p in messages["event"]["event"]["pantry"] if p["missing"]] == ["Sel"]

    for action, cle_produit in (("present", "sel"), ("missing", "poivre"), ("remove", "poivre")):
        await client.send_json_auto_id(
            {"type": "cookbook_menu/stock/update", "action": action, "key": cle_produit}
        )
        recus = [await client.receive_json(), await client.receive_json()]
        assert any(m.get("type") == "result" and m["success"] for m in recus)

    await client.send_json_auto_id({"type": "cookbook_menu/stock/update", "action": "missing"})
    assert (await client.receive_json())["error"]["code"] == "invalid_format"
    await client.send_json_auto_id(
        {"type": "cookbook_menu/stock/update", "action": "missing", "key": "inconnu"}
    )
    assert (await client.receive_json())["error"]["code"] == "not_found"
    for message in (
        {"type": "cookbook_menu/stock/subscribe", "config_entry_id": "x"},
        {"type": "cookbook_menu/stock/update", "action": "present", "key": "sel", "config_entry_id": "x"},
    ):
        await client.send_json_auto_id(message)
        assert (await client.receive_json())["error"]["code"] == "not_found"


async def test_voix_action_et_llm(hass: HomeAssistant, mock_client, config_entry) -> None:
    from homeassistant.components import conversation
    from homeassistant.core import Context
    from homeassistant.helpers import llm
    from homeassistant.setup import async_setup_component

    await installer(hass, config_entry)
    resultat = await conversation.async_converse(
        hass, "il n'y a plus d'huile d'olive", None, Context(), language="fr"
    )
    assert resultat.response.speech["plain"]["speech"] == "C'est noté, huile d'olive est dans les courses."
    assert "Huile d'olive" in await courses(hass)
    resultat = await conversation.async_converse(
        hass, "on n'a plus de papier toilette", None, Context(), language="fr"
    )
    assert "papier toilette" in resultat.response.speech["plain"]["speech"]
    resultat = await conversation.async_converse(hass, "we're out of eggs", None, Context(), language="en")
    assert resultat.response.speech["plain"]["speech"] == "Noted, eggs is on the shopping list."

    await hass.services.async_call("cookbook_menu", "out_of_stock", {"product": "Lessive"}, blocking=True)
    assert "Lessive" in await courses(hass)

    assert await async_setup_component(hass, "llm", {})
    contexte = llm.LLMContext(
        platform="test", context=Context(), language="fr", assistant="conversation", device_id=None
    )
    api = await llm.async_get_api(hass, llm.LLM_API_ASSIST, contexte)
    reponse = await api.async_call_tool(
        llm.ToolInput(tool_name="cookbook_menu__out_of_stock", tool_args={"product": "Beurre"})
    )
    assert reponse == {"success": True, "added_to_shopping_list": "Beurre"}
    reserve = await api.async_call_tool(llm.ToolInput(tool_name="cookbook_menu__get_stock", tool_args={}))
    assert reserve["success"] and "pantry" in reserve and "fridge" in reserve

    await hass.config_entries.async_unload(config_entry.entry_id)
    resultat = await conversation.async_converse(hass, "il n'y a plus de sel", None, Context(), language="fr")
    assert resultat.response.speech["plain"]["speech"] == "Cookbook Menu n'est pas configuré."


async def test_cas_limites_de_la_reserve(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, pantry=["Sel"])  # l'huile d'olive n'est plus au placard
    planificateur = config_entry.runtime_data.planner
    await ajouter(hass, "couscous")
    # « huile d'olive » sans quantité : cocher la range au frigo, décocher l'en sort.
    await cocher(hass, "Huile d'olive")
    assert "huile olive" in planificateur.stockage.donnees.frigo
    await cocher(hass, "Huile d'olive", "needs_action")
    assert "huile olive" not in planificateur.stockage.donnees.frigo

    # Plat cuisiné : les ingrédients sans quantité ne changent pas le frigo.
    await cocher(hass, "Huile d'olive")
    plat = planificateur.menu[0]
    planificateur.async_modifier_plat(plat.uid, fait=True)
    assert "huile olive" in planificateur.stockage.donnees.frigo

    # Produit de placard au frigo, signalé manquant : il rejoint le placard, à racheter.
    planificateur.async_reserve_manquant("huile olive")
    donnees = planificateur.stockage.donnees
    assert "huile olive" not in donnees.frigo and donnees.placard_epuise == {"huile olive": "Huile d'olive"}
    planificateur.async_reserve_present("huile olive")

    # Autre produit au frigo, plus demandé par le menu : signalé manquant, il passe en maison.
    donnees.frigo["carotte"] = {"nom": "Carotte", "quantites": {"pièce": 2}, "expire": "2026-09-20"}
    planificateur.async_reserve_manquant("carotte")
    assert donnees.maison["carotte"]["present"] is False

    # Supprimer une ligne de placard manquant utilisée par le menu : « j'en ai ».
    await ajouter(hass, "carry")
    await ajouter_course(hass, "sel")
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Sel (0,5 c. à c.)"}, blocking=True
    )
    assert planificateur.stockage.donnees.placard_epuise == {}


async def test_index_du_placard(hass: HomeAssistant, mock_client, config_entry, hass_ws_client) -> None:
    """Story 2.11 : un produit de placard ajouté à la main rejoint le placard, pas la maison."""
    await installer(hass, config_entry, pantry=["Sel"])
    planificateur = config_entry.runtime_data.planner
    donnees = planificateur.stockage.donnees

    await ajouter_course(hass, "Ras el hanout")
    assert (await courses(hass))["Ras el hanout"]["description"] == "manque au placard"
    assert donnees.maison == {} and donnees.placard_ajouts == {"ras el hanout": "Ras el hanout"}
    await cocher(hass, "Ras el hanout")
    assert {"key": "ras el hanout", "name": "Ras el hanout", "missing": False} in planificateur.reserve()[
        "pantry"
    ]

    # Désormais au placard : les recettes ne le demandent plus.
    await ajouter_course(hass, "Huile d'olive")
    await cocher(hass, "Huile d'olive")
    await ajouter(hass, "couscous")
    assert not any(libelle.startswith("Huile") for libelle in await courses(hass))

    # Carte : ajout direct (présent), produit de la maison déplacé, sortie du placard.
    client = await hass_ws_client(hass)
    for message in (
        {"action": "to_pantry", "name": "Sirop de sureau"},
        {"action": "to_pantry", "names": ["Riz basmati", "Quinoa", "riz basmati"]},
        {"action": "to_pantry", "name": "  "},
        {"action": "to_pantry", "key": "inconnu"},
        {"action": "to_pantry"},
    ):
        await client.send_json_auto_id({"type": "cookbook_menu/stock/update", **message})
        await client.receive_json()
    assert donnees.placard_ajouts["sirop sureau"] == "Sirop de sureau"
    assert "sirop sureau" not in donnees.placard_epuise
    assert (donnees.placard_ajouts["riz basmati"], donnees.placard_ajouts["quinoa"]) == (
        "Riz basmati",
        "Quinoa",
    )
    # Propositions de l'index : ni ce qui est déjà au placard, ni les variantes d'une famille présente.
    await client.send_json_auto_id({"type": "cookbook_menu/stock/subscribe"})
    await client.receive_json()
    suggestions = {p["name"] for p in (await client.receive_json())["event"]["suggestions"]}
    assert not {"Ras el hanout", "Quinoa", "Riz basmati", "Huile d'olive", "Sel", "Gros sel"} & suggestions
    assert {"Cumin", "Pâtes", "Lentilles corail"} <= suggestions

    await ajouter_course(hass, "Papier toilette")
    planificateur.async_reserve_au_placard(cle_produit="papier toilette")
    assert donnees.maison == {} and donnees.placard_epuise["papier toilette"] == "Papier toilette"

    planificateur.async_reserve_retirer("sel")  # produit des options
    planificateur.async_reserve_retirer("ras el hanout")  # produit rangé à la main
    cles = {p["key"] for p in planificateur.reserve()["pantry"]}
    assert "sel" not in cles and "ras el hanout" not in cles
    assert donnees.placard_retires == ["sel"]
    # « Il n'y a plus de sel » le remet au placard, à racheter.
    await ajouter_course(hass, "Sel")
    assert donnees.placard_retires == [] and donnees.placard_epuise["sel"] == "Sel"


async def test_migration_de_la_maison_vers_le_placard() -> None:
    from custom_components.cookbook_menu.store import DonneesPlanificateur

    donnees = DonneesPlanificateur.depuis_dict(
        {
            "maison": {
                "ras el hanout": {"nom": "Ras el hanout", "present": False, "description": None},
                "riz basmati": {"nom": "Riz basmati", "present": True, "description": None},
                "papier toilette": {"nom": "Papier toilette", "present": True, "description": None},
            }
        }
    )
    assert list(donnees.maison) == ["papier toilette"]
    assert donnees.placard_ajouts == {"ras el hanout": "Ras el hanout", "riz basmati": "Riz basmati"}
    assert donnees.placard_epuise == {"ras el hanout": "Ras el hanout"}
    assert DonneesPlanificateur.depuis_dict(donnees.en_dict()) == donnees
