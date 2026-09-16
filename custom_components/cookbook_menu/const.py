"""Constantes de l'intégration Cookbook Menu."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cookbook_menu"

CONF_SERVINGS: Final = "servings"
CONF_EXCLUDED_CATEGORIES: Final = "excluded_categories"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"
CONF_PANTRY: Final = "pantry"
CONF_PANTRY_REMINDER: Final = "pantry_reminder"
CONF_SYNC_MENU_ENTITY: Final = "sync_menu_entity"
CONF_SYNC_SHOPPING_ENTITY: Final = "sync_shopping_entity"

DEFAULT_SERVINGS: Final = 2
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 30
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

# Nombre maximal d'appels simultanés à l'API Cookbook lors du chargement des détails.
MAX_PARALLEL_REQUESTS: Final = 4
