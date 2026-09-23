"""Todo lists: "Menu de la semaine" and "Liste de courses"."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CookbookMenuConfigEntry
from .const import DOMAIN
from .libelles import libelles
from .planner import Planificateur, lire_couverts
from .store import PlatMenu

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CookbookMenuConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a config entry's lists."""
    async_add_entities([MenuTodoListEntity(entry), CoursesTodoListEntity(entry)])


class CookbookMenuEntity(TodoListEntity):
    """Common base: service device, translated name, subscription to the planner."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: CookbookMenuConfigEntry, cle: str) -> None:
        self.planificateur: Planificateur = entry.runtime_data.planner
        self._attr_translation_key = cle
        self._attr_unique_id = f"{entry.entry_id}_{cle}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Nextcloud",
            model="Cookbook",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.planificateur.async_ecouter(self._async_rafraichir))
        self.async_on_remove(self.planificateur.coordinateur.async_add_listener(self._async_rafraichir))
        self._async_rafraichir(ecrire=False)

    @property
    def available(self) -> bool:
        return self.planificateur.coordinateur.last_update_success

    @callback
    def _async_rafraichir(self, ecrire: bool = True) -> None:
        self._attr_todo_items = self._elements()
        if ecrire:
            self.async_write_ha_state()

    def _elements(self) -> list[TodoItem]:  # pragma: no cover - abstract
        raise NotImplementedError


class MenuTodoListEntity(CookbookMenuEntity):
    """Weekly menu: one dish per row, day as the due date, servings in the description."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "menu")

    def _description(self, plat: PlatMenu) -> str:
        textes = libelles(self.hass)
        morceaux = [textes["un_couvert"] if plat.servings == 1 else textes["couverts"].format(n=plat.servings)]
        if plat.recipe_id is None:
            morceaux.append(textes["sans_recette"])
        elif self.planificateur.recette_du_plat(plat) is None:
            morceaux.append(textes["introuvable"])
        return ", ".join(morceaux)

    def _elements(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=plat.uid,
                summary=plat.summary,
                status=TodoItemStatus.COMPLETED if plat.done else TodoItemStatus.NEEDS_ACTION,
                due=plat.day,
                description=self._description(plat),
            )
            for plat in self.planificateur.menu
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        jour = item.due.date() if isinstance(item.due, datetime) else item.due
        self.planificateur.async_ajouter_plat(
            item.summary or "",
            jour=jour,
            couverts=lire_couverts(item.description),
            fait=item.status == TodoItemStatus.COMPLETED,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        # HA sends the complete item (existing fields merged with the changes).
        self.planificateur.async_modifier_plat(
            item.uid or "",
            texte=item.summary,
            jour=item.due.date() if isinstance(item.due, datetime) else item.due,
            couverts=lire_couverts(item.description),
            fait=item.status == TodoItemStatus.COMPLETED,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self.planificateur.async_supprimer_plats(uids)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        self.planificateur.async_deplacer_plat(uid, previous_uid)


class CoursesTodoListEntity(CookbookMenuEntity):
    """Shopping list: products computed from the menu, plus lines added by hand."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "shopping")

    def _elements(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=ligne.uid,
                summary=ligne.libelle,
                status=TodoItemStatus.COMPLETED if ligne.fait else TodoItemStatus.NEEDS_ACTION,
                description=ligne.description,
            )
            for ligne in self.planificateur.liste_de_courses()
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        self.planificateur.async_ajouter_course(
            item.summary or "", item.description, fait=item.status == TodoItemStatus.COMPLETED
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        self.planificateur.async_modifier_course(
            item.uid or "",
            texte=item.summary,
            description=item.description,
            fait=item.status == TodoItemStatus.COMPLETED,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self.planificateur.async_supprimer_courses(uids)
