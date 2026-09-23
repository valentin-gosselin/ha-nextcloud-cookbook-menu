# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [1.3.0] - 2026-09-23

### Added
- Several timers at once, to follow several dishes: the integration exposes its own "Timer 1, 2, 3..." sensors (1 to 10, set in the options) with the end time and the step they come from. The *Timer entities* option now accepts several `timer.*` entities: the first idle one is used.
- `stop_timer` action: stops one timer (or all of them) and cancels the timer entity it was using. The cross in the card calls it.
- `start_timer` answers the timer number and the entity used, and the event carries them too.

## [1.2.0] - 2026-09-23

### Added
- Timers in Home Assistant: a timer started from a recipe also starts an Assist timer on the voice device chosen in the options (it rings there), starts the chosen `timer` entity, and fires the `nextcloud_cookbook_menu_timer_started` event for automations. New `start_timer` action. With nothing configured, the countdown in the card works as before.
- Stock card: a *Remove from stock* button on every product, to throw away something expired or fix a mistake.
- Recurring products: what goes outside the menu (butter for toast, milk, coffee) comes back on the list at its own pace, once a week by default, adjustable per product in the stock card.

### Changed
- Purchases use real pack sizes: a recipe asking for 10 g of butter buys a 250 g pack, nine eggs become a box of twelve. What is left over serves the next dishes instead of buying again every week.
- Shelf life per product: garlic, onions and potatoes 30 days, eggs 21, tomatoes and salad 5, minced meat 2, instead of 7 days for everything fresh. An unknown product now counts 7 days and no longer 60.
- Cuts of meat and fish are recognised (flank steak, rib steak, duck breast, sea bream...): they were filed as groceries, hence kept for 60 days.
- Stock card in tabs (*To buy again*, *Bought for the menu*, *Bought regularly*, *Always in stock*, *Household*) with a counter on each, and compact rows with icon buttons: the card fits one screen instead of unrolling the whole stock. The chosen tab is remembered on the device.
- The sections of the stock card say what they do: *Always in stock* (in stock or missing) and *Bought for the menu* (quantities and expiry).
- Timers are named "Step 3 - Caesar salad" instead of the recipe name alone.
- A product that keeps (the pantry index: baking powder, honey, pasta, canned food...) checked on the shopping list joins the **pantry**, not the fridge. Products already in the fridge that are in the index are moved there on update.

## [1.1.0] - 2026-09-19

### Added
- `custom:cookbook-recipes-card`: browse the recipes as a grid of thumbnails, with search and a filter per category, without going through the menu. The recipe opened from this card offers the day, the servings and adding to the menu.
- Photos are served as thumbnails (`.../image/<entry>/<recipe>/thumb`) instead of full size, for the grid.

### Fixed
- The nightly task (consumption, expiry) ran outside the Home Assistant event loop, which is not allowed for code that touches the state.
- The Lovelace resource left by the `cookbook_menu` domain (before 1.0.0) is removed automatically.

## [1.0.0] - 2026-09-18

First public release.

### Changed
- The domain becomes `nextcloud_cookbook_menu` and the integration is called "Nextcloud Cookbook Menu". The menu and the stock of a `cookbook_menu` installation are picked up automatically, but the entry has to be deleted and added again.
- The "check the pantry" line and its option are replaced by the stock. Lines added by hand become household products.
- Home Assistant 2026.9.0 or newer.

### Fixed
- Voice: a French sentence said to a Home Assistant set to English was parsed with the English rules ("Ajoute une salade César au menu jeudi pour quatre" became a free dish with no recipe, no day and no servings). The language of the sentence now wins over the language of the pipeline. English no longer says "on tomorrow" either.

### Added
- Voice: many more wordings understood without an LLM (add to the menu, ask for the menu, remove, history, "we're out of"), in French and in English. 132 real sentences are replayed by every test run, counter-examples included ("add butter to my shopping list" must not create a dish).
- Stock card: the *Add to pantry* field opens the list of known products not yet in the pantry, filtered as you type, with multiple selection. Free text is still accepted.
- An index of about 300 pantry products (spices, dried herbs, condiments, pasta, rice, flours, canned food...): a product added by hand that belongs to it joins the pantry instead of the household. Stock card: add to the pantry, move a household product to the pantry, remove from the pantry. Timers are shown inside the recipe view.
- Stock: pantry (in stock or missing), fridge (checking a shopping line means buying it; cooked or past dishes use their share; leftovers are reused; 7 days for fresh products, 60 for groceries) and household (purchases outside the menu). `custom:cookbook-stock-card` card, "we're out of..." sentence, `out_of_stock` action, LLM tools.
- Purchase units: garlic in cloves or heads, herbs in bunches, vegetables by the piece, butter by weight, sachets and tins. Whites and yolks join the eggs, lemon juice joins the lemons. Water and bay leaves are pantry staples by default.
- Recipe view in the card: photo, times, ingredients scaled to the servings, steps you can check off, timers started from the durations in the steps, screen kept on.
- `custom:cookbook-menu-card` dashboard card, registered automatically: recipe search as you type, day, servings, add, and the menu with "cooked" and removal.
- *Recipe to add* (every recipe by name), *Day*, *Servings* entities and an *Add to menu* button.
- "Sign in with Nextcloud" (Login Flow v2): no need to create and copy an app password. Entering one by hand is still possible.
- Full documentation (README), `quality_scale.yaml` self-assessment, icon and logo.
- Dish history: `get_history` action, spoken question "when did we last eat curry?", adjustable retention. `new_week` keeps upcoming dishes.
- Tools for LLM conversation agents (Assist API): search a recipe, add to the menu, remove, read the menu, look at the history.
- Voice with the default Assist agent, in French and in English: add a dish to the menu (day and servings included), ask what is for dinner, remove a dish.
- Optional copy of the menu and the shopping list to existing to-do lists (the one you open at the store), never touching lines added elsewhere. Items checked in the target list are brought back.
- `add_to_menu`, `remove_from_menu`, `set_servings`, `new_week` and `search_recipes` actions, with responses scripts can use. Days can be written out ("thursday", "tomorrow").
- Pantry: staples never added to the shopping list (adjustable list), with a reminder line to check before leaving. A pantry staple added by hand is marked missing and goes back to the pantry once checked.
- A *Shopping list* computed from the menu: quantities scaled to the servings, products merged across recipes, rounded to what you buy, sorted by aisle. Checked lines and lines added by hand are never overwritten.
- A *Weekly menu* list: one dish per line, linked automatically to the closest recipe (accents and typos tolerated), day as the due date, servings adjustable in the description.
- Configuration from the UI (URL, user, app password), with a connection test, re-authentication and reconfiguration.
- Household options: default servings, excluded categories, refresh interval.
- Parsing of French ingredient lines (quantities, fractions, ranges, units, sections, notes, multiple lines) and a merge key per product. Validated against a real corpus of 545 lines.
- Reading Nextcloud Cookbook recipes with a cache (details reloaded only when the recipe changed) and diagnostics with no secrets.
- Skeleton of the `nextcloud_cookbook_menu` integration, CI (hassfest, HACS, ruff, pytest), HACS release and a deployment script to the development Home Assistant.
