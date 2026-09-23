# Contributing

Thanks for taking a look. Issues and pull requests are welcome.

## Getting set up

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/pytest -q --cov=custom_components.nextcloud_cookbook_menu
docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest
```

The test suite is expected to stay at 100 % coverage: a pull request that adds code adds its tests.

## House rules

- Comments, docstrings and documentation are written in English.
- Identifiers are in French, because the domain vocabulary is (`placard` is the pantry, `frigo` the fridge, `couverts` the servings). Keep the existing names rather than mixing languages.
- No em dash or en dash anywhere, and no emoji in the code.
- User-facing strings live in `translations/`, in `libelles.py` for the list items, and in the `TEXTES` tables of the card.

## Adding a language

See the *Languages* section of the README: the interface alone is not enough, the parser and the voice sentences have to follow. Start with the tests, they say what is expected.

## Reporting a bug

Please include your Home Assistant version, the integration version, and the relevant part of the log with debug enabled:

```yaml
logger:
  logs:
    custom_components.nextcloud_cookbook_menu: debug
```
