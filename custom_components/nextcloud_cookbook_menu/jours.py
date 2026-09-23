"""Days written out in words ("thursday", "tomorrow") converted to a date."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .ingredients.normalize import sans_accents

_JOURS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}  # fmt: skip
_RELATIFS = {
    "aujourd hui": 0, "ce soir": 0, "ce midi": 0, "today": 0, "tonight": 0,
    "demain": 1, "tomorrow": 1, "apres demain": 2,
}  # fmt: skip


def lire_jour(valeur: str | date | None, aujourdhui: date) -> date | None:
    """Date matching `valeur`: a date, ISO string, weekday name (next occurrence), or relative term.

    Raises ValueError if the text isn't understood.
    """
    if valeur is None or isinstance(valeur, date):
        return valeur
    if re.fullmatch(r"\s*\d{4}-\d{2}-\d{2}\s*", valeur):
        return date.fromisoformat(valeur.strip())
    texte = re.sub(r"[^a-z]+", " ", sans_accents(valeur)).strip()
    if not texte:
        return None
    if texte in _RELATIFS:
        return aujourdhui + timedelta(days=_RELATIFS[texte])
    texte = re.sub(r"^(?:le|ce|pour|on)\s+", "", texte)
    premier = texte.split()[0]
    if premier in _JOURS:
        ecart = (_JOURS[premier] - aujourdhui.weekday()) % 7
        if "prochain" in texte or "next" in texte:
            ecart = ecart or 7
        return aujourdhui + timedelta(days=ecart)
    raise ValueError(valeur)
