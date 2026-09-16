"""Traitement des ingrédients : analyse des lignes, unités, clés de fusion.

Code Python pur, sans dépendance à Home Assistant, pour être testable isolément.
"""

from .normalize import cle
from .parser import Ingredient, analyser

__all__ = ["Ingredient", "analyser", "cle"]
