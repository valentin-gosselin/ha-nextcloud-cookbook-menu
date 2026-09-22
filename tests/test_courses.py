"""Liste de courses dans Home Assistant : calcul, achats et frigo (stories 2.2 et 2.10)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.nextcloud_cookbook_menu.api import CookbookConnectionError, Recipe
from custom_components.nextcloud_cookbook_menu.ingredients import frigo
from custom_components.nextcloud_cookbook_menu.ingredients.aisles import Rayon

from .test_menu import ajouter, elements

COURSES = "todo.valentin_cloud_exemple_fr_liste_de_courses"
MENU = "todo.valentin_cloud_exemple_fr_menu_de_la_semaine"


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


async def courses(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    return {ligne["summary"]: ligne for ligne in await elements(hass, COURSES)}


async def cocher(hass: HomeAssistant, libelle: str, statut: str = "completed") -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "update_item", {"entity_id": COURSES, "item": libelle, "status": statut}, blocking=True
    )


async def modifier_plat(hass: HomeAssistant, plat: str, **donnees: Any) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "update_item", {"entity_id": MENU, "item": plat, **donnees}, blocking=True
    )


async def test_courses_suivent_le_menu(hass: HomeAssistant, entree) -> None:
    assert await courses(hass) == {}
    await ajouter(hass, "salade cesar")
    lignes = await courses(hass)
    assert lignes["Citron (1)"]["description"] == "Salade César au poulet pour 2"
    assert not any(libelle.startswith("À vérifier") for libelle in lignes)  # plus de ligne de rappel
    assert hass.states.get(COURSES).state == str(len(lignes))
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": MENU, "item": "Salade César au poulet"}, blocking=True
    )
    assert await courses(hass) == {}


async def test_changer_les_couverts_recalcule(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "salade cesar")
    assert "Escalope de poulet (1)" in await courses(hass)
    await modifier_plat(hass, "Salade César au poulet", description="pour 8")
    assert "Escalope de poulet (4)" in await courses(hass)


async def test_cocher_c_est_acheter(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    frigo = entree.runtime_data.planner.stockage.donnees.frigo
    assert frigo["tomate"]["quantites"] == {"pièce": 2}
    assert frigo["tomate"]["expire"] == "2026-09-21"  # tomates : 5 jours (table par produit)
    ligne = (await courses(hass))["Tomates (2)"]
    assert ligne["status"] == "completed"
    assert ligne["description"] == "Carry de poulet pour 6, déjà au frigo : 2"

    # Plus de couverts : il ne manque que la différence.
    await ajouter(hass, "couscous", description="pour 2")
    ligne = (await courses(hass))["Tomates (1)"]
    assert ligne["status"] == "needs_action"
    assert "déjà au frigo : 2" in ligne["description"]

    # Décocher annule l'achat.
    await cocher(hass, "Tomates (1)")
    await cocher(hass, "Tomates (3)", "needs_action")
    assert "tomate" not in frigo
    assert (await courses(hass))["Tomates (3)"]["status"] == "needs_action"


async def test_epicerie_expire_plus_tard(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "couscous")
    await cocher(hass, "Merguez (4)")
    donnees = entree.runtime_data.planner.stockage.donnees
    assert donnees.frigo["merguez"]["expire"] == "2026-09-23"  # frais : 7 jours

    # Épicerie : 60 jours (produit sans rapport avec l'index du placard).
    frigo.ajouter(donnees.frigo, "sachet", "Sachet", {"pièce": 1}, Rayon.EPICERIE_SALEE, date(2026, 9, 16))
    assert donnees.frigo["sachet"]["expire"] == "2026-11-15"

    # Les pois chiches se gardent : ils rejoignent le placard, pas le frigo (story 2.14).
    await cocher(hass, "Pois chiches (150 g)")
    assert "pois chiche" not in donnees.frigo
    assert donnees.placard_ajouts == {"pois chiche": "Pois chiches"}
    assert not any(libelle.startswith("Pois chiches") for libelle in await courses(hass))

    # Produit sans quantité : coché il entre au frigo, décoché il en sort.
    await ajouter(hass, "cordon bleu")
    await cocher(hass, "Beurre")
    assert "beurre" in donnees.frigo
    await cocher(hass, "Beurre", "needs_action")
    assert "beurre" not in donnees.frigo


async def test_recette_modifiee_apres_achat(hass: HomeAssistant, entree, recettes) -> None:
    """Critère du party mode du 16/09 : pas de réapparition silencieuse."""
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Oignons (2)")
    carry = recettes["2176038"]
    recettes["2176038"] = Recipe(
        **{**{f: getattr(carry, f) for f in carry.__slots__}, "ingredients": ("300 g d'oignons",)}
    )
    await entree.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    ligne = (await courses(hass))["Oignons (1)"]
    assert ligne["status"] == "needs_action"
    assert "déjà au frigo : 2" in ligne["description"]


async def test_supprimer_une_ligne_vaut_j_en_ai(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": COURSES, "item": "Thym (1 branche)"}, blocking=True
    )
    assert (await courses(hass))["Thym (1 branche)"]["status"] == "completed"
    assert entree.runtime_data.planner.stockage.donnees.frigo["thym"]["quantites"] == {"branche": 1}


async def test_plat_cuisine_consomme_le_frigo(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    await ajouter(hass, "couscous", description="pour 2")
    await cocher(hass, "Tomates (1)")
    frigo = entree.runtime_data.planner.stockage.donnees.frigo
    assert frigo["tomate"]["quantites"] == {"pièce": 3}

    await modifier_plat(hass, "Carry de poulet", status="completed")
    assert frigo["tomate"]["quantites"]["pièce"] == pytest.approx(3 - 200 / 120, abs=1e-3)
    assert (await courses(hass))["Tomates (1)"]["status"] == "completed"  # le couscous reste couvert

    # Décoché par erreur : sa part revient au frigo.
    await modifier_plat(hass, "Carry de poulet", status="needs_action")
    assert frigo["tomate"]["quantites"]["pièce"] == pytest.approx(3, abs=1e-3)


async def test_date_passee_consomme_et_restes_reutilises(hass: HomeAssistant, entree, freezer) -> None:
    await ajouter(hass, "carry", due_date="2026-09-16", description="pour 6")
    await cocher(hass, "Oignons (2)")
    planificateur = entree.runtime_data.planner
    freezer.move_to("2026-09-17 00:05:00+02:00")
    planificateur.async_consommer()
    await hass.async_block_till_done()
    assert planificateur.menu[0].consumed
    assert "oignon" not in planificateur.stockage.donnees.frigo  # 200 g utilisés = 2 oignons

    # Restes : 1 citron acheté pour ½ citron, réutilisé la semaine suivante.
    await ajouter(hass, "salade cesar")
    await cocher(hass, "Citron (1)")
    await modifier_plat(hass, "Salade César au poulet", status="completed")
    assert planificateur.stockage.donnees.frigo["citron"]["quantites"] == {"pièce": 0.5}
    await ajouter(hass, "salade cesar", description="pour 1")
    assert (await courses(hass))["Citron (1)"]["status"] == "completed"

    # Passé sa durée de conservation (21 jours pour un citron), le reste est oublié.
    freezer.move_to("2026-10-09 00:05:00+02:00")
    planificateur.async_consommer()
    assert "citron" not in planificateur.stockage.donnees.frigo


async def test_ligne_calculee_non_renommable(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "salade cesar")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            TODO_DOMAIN,
            "update_item",
            {"entity_id": COURSES, "item": "Citron (1)", "rename": "Citrons bio"},
            blocking=True,
        )
    planificateur = entree.runtime_data.planner
    with pytest.raises(ServiceValidationError):
        planificateur.async_modifier_course("inconnu", texte=None, description=None, fait=True)
    with pytest.raises(ServiceValidationError):
        planificateur.async_ajouter_course("  ")


async def test_panne_nextcloud_ne_perd_pas_le_frigo(hass: HomeAssistant, entree, mock_client) -> None:
    await ajouter(hass, "carry", description="pour 6")
    await cocher(hass, "Tomates (2)")
    coordinateur = entree.runtime_data.coordinator
    mock_client.async_get_recipes.side_effect = CookbookConnectionError("coupure")
    await coordinateur.async_refresh()
    mock_client.async_get_recipes.side_effect = None
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    assert (await courses(hass))["Tomates (2)"]["status"] == "completed"


async def test_meme_recette_deux_fois(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", description="pour 2")
    await ajouter(hass, "carry", description="pour 4")
    assert (await courses(hass))["Ail (6 gousses)"]["description"] == "Carry de poulet pour 6"
