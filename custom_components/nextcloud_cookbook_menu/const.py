"""Constants for the Nextcloud Cookbook Menu integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nextcloud_cookbook_menu"

CONF_SERVINGS: Final = "servings"
CONF_EXCLUDED_CATEGORIES: Final = "excluded_categories"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"
CONF_PANTRY: Final = "pantry"
CONF_SYNC_MENU_ENTITY: Final = "sync_menu_entity"
CONF_SYNC_SHOPPING_ENTITY: Final = "sync_shopping_entity"
CONF_HISTORY_MONTHS: Final = "history_months"
CONF_TIMER_DEVICE: Final = "timer_device"
CONF_TIMER_ENTITY: Final = "timer_entity"
CONF_TIMERS_COUNT: Final = "timers_count"

# Event fired for each timer started from the recipe card.
EVENEMENT_MINUTEUR: Final = "nextcloud_cookbook_menu_timer_started"

DEFAULT_SERVINGS: Final = 2
DEFAULT_HISTORY_MONTHS: Final = 24
DEFAULT_TIMERS_COUNT: Final = 3
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 30
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

# Maximum number of concurrent calls to the Cookbook API when loading details.
MAX_PARALLEL_REQUESTS: Final = 4
