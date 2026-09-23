"""Corpus of voice command variants, understood without an LLM by the default Assist agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant

from .test_assist import dire, entree  # noqa: F401

CORPUS: dict[str, list[Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "phrases_vocales.json").read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, date_figee) -> None:
    """Sentences in French, on 2026-09-16: "jeudi" means the 17th."""
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


def _echecs(resultats: list[tuple[str, str]]) -> str:
    return "\n".join(f"  {texte} -> {souci}" for texte, souci in resultats)


async def test_variantes_ajout(hass: HomeAssistant, entree) -> None:  # noqa: F811
    planificateur = entree.runtime_data.planner
    echecs: list[tuple[str, str]] = []
    for cas in CORPUS["ajout"]:
        await dire(hass, cas["texte"])
        plats = planificateur.menu
        if len(plats) != 1:
            echecs.append((cas["texte"], f"{len(plats)} plats au menu"))
        else:
            plat = plats[0]
            attendu = (cas["plat"], cas.get("jour"), cas.get("couverts", 2))
            obtenu = (plat.summary, plat.day.isoformat() if plat.day else None, plat.servings)
            if obtenu != attendu:
                echecs.append((cas["texte"], f"{obtenu} au lieu de {attendu}"))
        planificateur.async_supprimer_plats([p.uid for p in planificateur.menu])
    assert not echecs, f"\n{_echecs(echecs)}"


async def test_phrases_qui_ne_sont_pas_des_commandes_du_menu(hass: HomeAssistant, entree) -> None:  # noqa: F811
    """Home Assistant's native lists and everything else must not land in the menu."""
    planificateur = entree.runtime_data.planner
    echecs: list[tuple[str, str]] = []
    for texte in CORPUS["hors_menu"]:
        await dire(hass, texte)
        if planificateur.menu:
            echecs.append((texte, f"a créé le plat « {planificateur.menu[0].summary} »"))
            planificateur.async_supprimer_plats([p.uid for p in planificateur.menu])
    assert not echecs, f"\n{_echecs(echecs)}"


async def test_variantes_menu(hass: HomeAssistant, entree) -> None:  # noqa: F811
    await dire(hass, "ajoute un carry au menu demain")
    echecs: list[tuple[str, str]] = []
    for texte in CORPUS["menu"]:
        reponse = await dire(hass, texte)
        # With no day stated, the response talks about today and announces the next dish.
        if "Carry de poulet" not in reponse:
            echecs.append((texte, reponse))
    assert not echecs, f"\n{_echecs(echecs)}"


async def test_variantes_retrait(hass: HomeAssistant, entree) -> None:  # noqa: F811
    planificateur = entree.runtime_data.planner
    echecs: list[tuple[str, str]] = []
    for texte in CORPUS["retrait"]:
        await dire(hass, "ajoute un carry au menu demain")
        reponse = await dire(hass, texte)
        if planificateur.menu:
            echecs.append((texte, reponse))
            planificateur.async_supprimer_plats([p.uid for p in planificateur.menu])
    assert not echecs, f"\n{_echecs(echecs)}"


async def test_variantes_historique(hass: HomeAssistant, entree) -> None:  # noqa: F811
    planificateur = entree.runtime_data.planner
    planificateur.stockage.donnees.historique = [
        {"day": "2026-09-01", "summary": "Carry de poulet", "servings": 2, "recipe_id": None}
    ]
    echecs: list[tuple[str, str]] = []
    for texte in CORPUS["historique"]:
        reponse = await dire(hass, texte)
        if "Carry de poulet" not in reponse:
            echecs.append((texte, reponse))
    assert not echecs, f"\n{_echecs(echecs)}"


async def test_variantes_manque(hass: HomeAssistant, entree) -> None:  # noqa: F811
    planificateur = entree.runtime_data.planner
    echecs: list[tuple[str, str]] = []
    for cas in CORPUS["manque"]:
        await dire(hass, cas["texte"])
        lignes = [ligne.libelle for ligne in planificateur.liste_de_courses()]
        if cas["produit"] not in lignes:
            echecs.append((cas["texte"], ", ".join(lignes) or "rien dans les courses"))
        donnees = planificateur.stockage.donnees
        donnees.maison.clear()
        donnees.placard_epuise.clear()
        donnees.placard_ajouts.clear()
        planificateur._signaler_changement()
    assert not echecs, f"\n{_echecs(echecs)}"
