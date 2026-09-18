# Cookbook Menu for Home Assistant

Plan the weekly menu from your **Nextcloud Cookbook** recipes and get the **shopping list built for you**: quantities scaled to the number of servings, identical products merged across recipes, rounded to what you actually buy, sorted by store aisle, without the pantry staples you always have at home.

> Résumé en français en bas de page.

- "Add a caesar salad to the menu on thursday for four" and the ingredients land in the shopping list.
- Change your mind, remove the dish or change the servings: the shopping list follows, and never un-checks what you already bought.
- Works from the UI, from automations and scripts, with the default Assist agent (French and English sentences) and with LLM conversation agents.
- Optionally copies the menu and the shopping list to the to-do lists your household already uses.

Nextcloud Cookbook has no shopping list feature ([nextcloud/cookbook#11](https://github.com/nextcloud/cookbook/issues/11), open since 2019): this integration fills that gap inside Home Assistant.

## Requirements

- Home Assistant **2026.9** or newer.
- A Nextcloud server with the **Cookbook** app (API 1.x, tested with Cookbook 0.11).
- A Nextcloud account. Signing in with Nextcloud creates the app password for you; you can also create one yourself.

## Installation

### HACS (recommended)

1. HACS > Integrations > menu > Custom repositories > add this repository, category *Integration*.
2. Install **Cookbook Menu**, then restart Home Assistant.

### Manual

Copy `custom_components/cookbook_menu` into the `custom_components` folder of your configuration, then restart Home Assistant.

## Configuration

Settings > Devices & services > Add integration > **Cookbook Menu**, then enter the address of your Nextcloud server and choose:

- **Sign in with Nextcloud (recommended)**: your Nextcloud login page opens; sign in and grant access. Home Assistant receives its own app password, listed as *Cookbook Menu (Home Assistant)* in Nextcloud Settings > Security, where it can be revoked.
- **Enter an app password**: create one in Nextcloud (Personal settings > Security > Devices & sessions) and enter it with your username.

*Verify SSL certificate* should only be disabled for a self-signed certificate. The connection is tested before the entry is created. If the access is revoked later, Home Assistant asks you to sign in again or enter a new app password (re-authentication). The URL, user and password can be changed with *Reconfigure*.

### Options

| Option | Default | Description |
|---|---|---|
| Default servings | 2 | Servings used when none is given. |
| Excluded categories | none | Recipe categories never offered (for example household products). |
| Pantry staples | salt, pepper, oils, vinegar, sugar, flour, common spices | Never added to the shopping list. "Oil", "vinegar", "salt" and "pepper" also cover their variants. |
| History retention | 24 months | Past dishes older than this are forgotten at each new week. |
| Copy the menu to / Copy the shopping list to | none | An existing to-do list that receives a copy (see below). |
| Refresh interval | 30 minutes | How often recipes are reloaded from Nextcloud. |

## Entities

Each configured account creates a service device with two to-do lists:

- **Weekly menu**: one dish per line. Type a dish name: it is linked to the closest recipe (accents, plurals and small typos are tolerated) and renamed to the exact recipe name. An ambiguous or unknown name stays a free dish that does not affect the shopping list. The due date is the planned day; write "for 4" or "4 servings" in the description to change the servings.
- **Shopping list**: products computed from the menu minus what is already in the fridge, plus missing pantry staples and household items, sorted by aisle.
  - Checking a line means you bought it (see *Stock* below); unchecking cancels the purchase.
  - Deleting a computed line means "I already have it".
  - Adding a product by hand marks it missing: a pantry staple, a fridge product or a household item.
  - Computed lines cannot be renamed.

## Dashboard card

The integration ships a card and registers it automatically (reload the browser once after installing):

```yaml
type: custom:cookbook-menu-card
title: Weekly menu   # optional
```

Type a few letters to find a recipe (accents are ignored), pick the day and the servings, then *Add to menu*. The menu is shown below: check a dish once cooked, or remove it.

Click a dish to open its recipe: photo, times, ingredients scaled to the servings (adjustable), numbered steps you can check off, and **timers**: every duration written in a step ("25 min", "1 h 30") is a button that starts a countdown, shown at the top of the recipe and in the card, which rings at the end. A *Keep screen on* button prevents the tablet from sleeping while cooking.

The same can be done without the card with the entities *Recipe to add*, *Day*, *Servings* and the *Add to menu* button.

## Stock: pantry, fridge and household

Cookbook Menu keeps track of what is at home without asking you to type anything:

- **Pantry** (the staples from the options, plus what you add): either in stock or missing. Say "we're out of olive oil" (or tap it in the stock card) and it goes to the shopping list; check it when bought and it is back in stock. A product added by hand that keeps for more than a week (spices, dried herbs, condiments, pasta, rice, flours, canned food: about 300 known products, variants included) joins the pantry. In the card, the *Add to pantry* field opens the list of known products not yet in the pantry, filtered as you type: check several at once, or add any product as typed. Products can also be removed from the pantry.
- **Fridge**: checking a shopping line means you bought it. The quantity goes to the fridge, a line stays checked while the fridge covers the menu, and only what is missing is asked for. A cooked dish (checked in the menu) or a dish whose day has passed uses its share. Leftovers are reused by the next dishes. Fresh products are forgotten after 7 days, groceries after 60.
- **Household**: items added by hand to the shopping list (toilet paper, a pan) join the stock once checked. They can be marked out of stock again, or removed from the stock.

```yaml
type: custom:cookbook-stock-card
```

The first time, the card asks you to check the pantry: everything is considered in stock, uncheck what is missing.

## Actions

| Action | Fields | Response |
|---|---|---|
| `cookbook_menu.add_to_menu` | `recipe` (text), `recipe_id` (exact id, optional), `day` (date, weekday, today, tomorrow), `servings` | dish, linked recipe, alternatives, changed shopping lines |
| `cookbook_menu.remove_from_menu` | `recipe` or `uid` | |
| `cookbook_menu.set_servings` | `recipe` or `uid`, `servings` | |
| `cookbook_menu.new_week` | | archived dishes |
| `cookbook_menu.get_history` | `recipe` (optional), `limit` | past dishes, most recent first |
| `cookbook_menu.search_recipes` | `query`, `limit` | recipes with a similarity score |
| `cookbook_menu.out_of_stock` | `product` | |

`config_entry_id` is optional when a single account is configured. Weekdays can be written in French or English ("jeudi", "thursday", "mercredi prochain").

`new_week` archives dishes that were checked or whose day has passed, keeps upcoming dishes and removes checked manual shopping lines.

## Voice

### Default Assist agent

The sentences are registered automatically, no configuration needed.

| Français | English |
|---|---|
| Ajoute une salade César au menu jeudi pour quatre | Add a caesar salad to the menu on thursday for four |
| Au menu dimanche mets une tartiflette | Put a tartiflette on the menu tomorrow |
| Qu'est-ce qu'on mange ce soir / vendredi | What's for dinner / What are we eating on friday |
| Retire le carry du menu | Remove the curry from the menu |
| Quand est-ce qu'on a mangé du carry | When did we last eat curry |
| Il n'y a plus d'huile d'olive | We're out of olive oil |

Adding, checking or removing shopping items uses the built-in Home Assistant list sentences ("add eggs to my shopping list").

### LLM conversation agents

With the Assist API enabled, agents get the tools `cookbook_menu__search_recipes`, `__add_to_menu`, `__remove_from_menu`, `__get_menu`, `__get_history`, `__out_of_stock` and `__get_stock`, and a short instruction: never copy ingredients into the shopping list themselves, ask which recipe is meant when a name is ambiguous.

## Copying to existing lists

If your household already opens another to-do list at the store, choose it in the options. Cookbook Menu stays the source of truth and:

- adds, updates and removes only the lines it created there, never the others;
- sends descriptions and due dates only if the target list supports them (the built-in *Shopping list* does not);
- brings back the lines checked in the target list.

## Examples

Start a new week every Monday morning:

```yaml
automation:
  - alias: "New menu week"
    triggers:
      - trigger: time
        at: "06:00:00"
    conditions:
      - condition: time
        weekday: mon
    actions:
      - action: cookbook_menu.new_week
```

Plan a dish from a script and tell what changed:

```yaml
script:
  plan_dish:
    fields:
      dish:
        selector:
          text:
    sequence:
      - action: cookbook_menu.add_to_menu
        data:
          recipe: "{{ dish }}"
          day: tomorrow
        response_variable: result
      - action: persistent_notification.create
        data:
          message: >-
            {{ result.dish }} planned, {{ result.shopping_items_changed | count }} shopping lines updated.
```

## How data is updated

- **Recipes**: the recipe list is polled every 30 minutes (configurable). A recipe's details are only downloaded again when it changed in Nextcloud.
- **Shopping list**: recomputed locally, instantly, whenever the menu, the options or the recipes change.
- **Storage**: the menu, check states and history are stored in Home Assistant (`.storage/cookbook_menu.<entry>`), not in Nextcloud.

## Known limitations

- Ingredients are free text in Nextcloud Cookbook. The parser is written for **French** first (and common English units), and is tested against 545 real ingredient lines. An unrecognised line keeps its original text, without quantity.
- Units that cannot be converted are listed side by side ("Tomatoes (70 g + 1)").
- Recipes without a number of servings are considered to serve 1.
- The menu and the shopping list are not written back to Nextcloud.

## Troubleshooting

- **"Invalid username or app password"**: prefer *Sign in with Nextcloud*; your account password is refused when two-factor authentication is enabled.
- **"This Nextcloud server does not offer sign-in from applications"**: use an app password instead.
- **"The Cookbook app was not found"**: check that the Cookbook app is installed and enabled for your user.
- **A dish is not linked to the right recipe**: rename the menu line with a more precise name, or use `search_recipes` then `add_to_menu`.
- **Diagnostics**: Settings > Devices & services > Cookbook Menu > menu > Download diagnostics. The password and the username are redacted.
- Debug logs:

```yaml
logger:
  logs:
    custom_components.cookbook_menu: debug
```

## Removal

Settings > Devices & services > Cookbook Menu > menu > Delete. The stored menu, shopping states and history are deleted with the entry. Then remove the integration from HACS (or delete `custom_components/cookbook_menu`) and restart Home Assistant. Nothing is changed in Nextcloud.

---

## En français

Cookbook Menu relie vos recettes **Nextcloud Cookbook** à Home Assistant.
- **Menu** : un plat dit ou tapé (« salade césar jeudi pour 4 ») rejoint le menu de la semaine.
- **Courses** : ses ingrédients arrivent dans la liste de courses, mis à l'échelle, fusionnés, arrondis à l'achat, rangés par rayon, sans les produits du placard.
- **Réserve** : placard, frigo et maison tenus à jour par les courses et le menu. Un produit qui se garde (ras el hanout, riz, farine...) ajouté à la main rejoint le placard.
- **Pilotage** : depuis l'interface, les automatisations, Assist (phrases en français) ou un agent LLM.
- **Synchronisation** : une recopie est possible vers la liste de courses que le foyer utilise déjà.

Installation par HACS (dépôt personnalisé), puis ajout de l'intégration : on saisit l'URL de Nextcloud et on choisit **Se connecter avec Nextcloud** (ou un mot de passe d'application saisi à la main). Toutes les options, actions et phrases sont décrites ci-dessus.

## License

MIT
