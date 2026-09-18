"""Phrases avec l'agent de conversation par défaut (story 3.1)."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant

from custom_components.nextcloud_cookbook_menu.assist import (
    _REPONSES,
    async_enregistrer_phrases,
    texte_courses,
)

from .test_courses import courses
from .test_menu import elements


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")  # un mercredi
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def dire(hass: HomeAssistant, texte: str, langue: str = "fr") -> str:
    resultat = await conversation.async_converse(hass, texte, None, Context(), language=langue)
    return resultat.response.speech["plain"]["speech"]


async def test_ajouter_au_menu(hass: HomeAssistant, entree) -> None:
    reponse = await dire(hass, "Ajoute une salade César au menu jeudi pour quatre")
    assert reponse.startswith("C'est noté : Salade César au poulet demain pour 4.")
    assert "produits ajoutés ou modifiés dans les courses" in reponse
    [plat] = await elements(hass)
    assert (plat["summary"], plat["due"], plat["description"]) == (
        "Salade César au poulet",
        "2026-09-17",
        "4 couverts",
    )
    assert "Escalope de poulet (2)" in await courses(hass)


async def test_ajouter_variantes(hass: HomeAssistant, entree) -> None:
    assert (await dire(hass, "mets du carry au menu de la semaine samedi")).startswith(
        "C'est noté : Carry de poulet samedi pour 2."
    )
    assert "ambigu" not in await dire(hass, "au menu dimanche mets une tartiflette")
    assert [p["summary"] for p in await elements(hass)] == ["Carry de poulet", "Tartiflette"]


async def test_ajouter_ambigu_et_libre(hass: HomeAssistant, entree) -> None:
    reponse = await dire(hass, "ajoute un gratin au menu")
    assert reponse.startswith("C'est noté : Gratin")
    assert "Sinon, il y a aussi Gratin" in reponse
    assert await dire(hass, "ajoute des restes au menu ce soir") == (
        "C'est noté : restes aujourd'hui, sans recette associée."
    )


async def test_qu_est_ce_qu_on_mange(hass: HomeAssistant, entree) -> None:
    assert await dire(hass, "qu'est-ce qu'on mange ce soir") == "Rien de prévu aujourd'hui."
    await dire(hass, "ajoute du carry au menu vendredi")
    assert await dire(hass, "qu'est-ce qu'on mange") == (
        "Rien de prévu aujourd'hui. Prochain plat : Carry de poulet vendredi."
    )
    await dire(hass, "ajoute une tartiflette au menu vendredi")
    assert await dire(hass, "on mange quoi vendredi") == "Vendredi : Carry de poulet et Tartiflette."
    await dire(hass, "ajoute une ratatouille au menu demain")
    assert await dire(hass, "c'est quoi le menu demain") == "Demain : Ratatouille."


async def test_retirer(hass: HomeAssistant, entree) -> None:
    await dire(hass, "ajoute du carry au menu vendredi")
    assert await dire(hass, "retire le carry du menu") == "C'est fait, Carry de poulet est retiré du menu."
    assert await elements(hass) == []
    assert await dire(hass, "enlève la tartiflette du menu") == "Je ne trouve pas tartiflette dans le menu."


async def test_anglais(hass: HomeAssistant, entree) -> None:
    await hass.config.async_update(language="en")
    reponse = await dire(hass, "add a caesar salad to the menu on friday for two", "en")
    assert reponse.startswith("Done: Salade César au poulet on Friday for 2.")
    assert await dire(hass, "what's for dinner on friday", "en") == "Friday: Salade César au poulet."
    assert await dire(hass, "what are we eating today", "en") == (
        "Nothing planned today. Next dish: Salade César au poulet on Friday."
    )
    assert await dire(hass, "remove caesar salad from the menu", "en") == (
        "Done, Salade César au poulet was removed from the menu."
    )


async def test_phrases_francaises_sur_un_home_assistant_en_anglais(hass: HomeAssistant, entree) -> None:
    """La langue de la phrase prime sur celle du pipeline (bug vu sur le HA de dev en anglais)."""
    await hass.config.async_update(language="en")
    reponse = await dire(hass, "Ajoute une salade César au menu jeudi pour quatre", langue="en")
    assert reponse.startswith("C'est noté : Salade César au poulet demain pour 4.")
    [plat] = await elements(hass)
    # La description suit la langue de Home Assistant, pas celle de la phrase.
    assert (plat["due"], plat["description"]) == ("2026-09-17", "4 servings")
    assert (await dire(hass, "Qu'est-ce qu'on mange demain", langue="en")).startswith("Demain : Salade")
    assert (await dire(hass, "il n'y a plus d'huile d'olive", langue="en")).startswith("C'est noté, huile")
    assert (await dire(hass, "Retire la salade César du menu", langue="en")) == (
        "C'est fait, Salade César au poulet est retiré du menu."
    )


async def test_phrases_anglaises_sur_un_home_assistant_en_francais(hass: HomeAssistant, entree) -> None:
    reponse = await dire(hass, "Add a caesar salad to the menu on thursday for four", langue="fr")
    assert reponse.startswith("Done: Salade César au poulet tomorrow for 4.")


async def test_sans_configuration(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)
    assert await dire(hass, "ajoute du carry au menu") == "Nextcloud Cookbook Menu n'est pas configuré."
    assert await dire(hass, "qu'est-ce qu'on mange") == "Nextcloud Cookbook Menu n'est pas configuré."
    assert await dire(hass, "retire le carry du menu") == "Nextcloud Cookbook Menu n'est pas configuré."


async def test_plat_manquant(hass: HomeAssistant, entree) -> None:
    assert await dire(hass, "ajoute jeudi au menu") == "Quel plat faut-il ajouter au menu ?"
    assert await elements(hass) == []


def test_texte_courses() -> None:
    textes = _REPONSES["fr"]
    assert texte_courses(0, textes) == ""
    assert texte_courses(1, textes) == " 1 produit ajouté ou modifié dans les courses."
    assert texte_courses(3, textes) == " 3 produits ajoutés ou modifiés dans les courses."


async def test_retrait_des_phrases(hass: HomeAssistant, entree) -> None:
    from homeassistant.components.conversation.agent_manager import get_agent_manager

    gestionnaire = get_agent_manager(hass)
    avant = len(gestionnaire.trigger_sentences)
    retirer = async_enregistrer_phrases(hass)
    assert len(gestionnaire.trigger_sentences) > avant
    retirer()
    assert len(gestionnaire.trigger_sentences) == avant


async def test_quand_a_t_on_mange(hass: HomeAssistant, entree) -> None:
    entree.runtime_data.planner.stockage.donnees.historique.extend(
        [
            {"day": "2026-08-15", "summary": "Carry de poulet", "recipe_id": "2176038", "servings": 2},
            {"day": "2026-07-01", "summary": "Carry de poulet", "recipe_id": "2176038", "servings": 2},
        ]
    )
    assert (
        await dire(hass, "quand est-ce qu'on a mangé du carry")
        == "La dernière fois : Carry de poulet, le 15 août 2026."
    )
    assert await dire(hass, "quand a-t-on fait une tartiflette") == "Pas de tartiflette dans l'historique."
    await hass.config.async_update(language="en")
    assert await dire(hass, "when did we last eat carry", "en") == "Last time: Carry de poulet, on August 15, 2026."
    await hass.config_entries.async_unload(entree.entry_id)
    assert await dire(hass, "quand a-t-on fait une tartiflette") == "Nextcloud Cookbook Menu n'est pas configuré."
