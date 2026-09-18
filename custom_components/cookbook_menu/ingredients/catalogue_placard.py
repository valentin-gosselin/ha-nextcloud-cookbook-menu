"""Index des produits de placard : ingrédients de cuisine qui se gardent plus d'une semaine.

Sert à ranger un produit ajouté à la main (liste de courses, carte, voix) : s'il figure ici,
il rejoint le placard (présent ou manquant) plutôt que la rubrique « maison ». Les noms sont
passés par la clé de fusion, donc accents, pluriels et articles n'ont pas d'importance.
"""

from __future__ import annotations

from difflib import get_close_matches
from functools import cache

from .normalize import cle

PRODUITS_PLACARD: tuple[str, ...] = (
    # Sel, poivre, épices moulues et entières
    "Sel", "Fleur de sel", "Gros sel", "Sel fin", "Poivre", "Poivre noir", "Poivre blanc", "Poivre gris",
    "Baies roses", "Poivre de Sichuan", "Cumin", "Coriandre moulue", "Graines de coriandre", "Curcuma",
    "Curry", "Paprika", "Paprika fumé", "Piment d'Espelette", "Piment de Cayenne", "Piment en poudre",
    "Chili en poudre", "Cannelle", "Bâton de cannelle", "Muscade", "Noix de muscade", "Gingembre moulu",
    "Clou de girofle", "Clous de girofle", "Cardamome", "Anis étoilé", "Badiane", "Fenugrec", "Carvi",
    "Fenouil en graines", "Graines de fenouil", "Graines de moutarde", "Safran", "Pistils de safran",
    "Quatre-épices", "Cinq-épices", "Ras el hanout", "Garam masala", "Colombo", "Tandoori",
    "Épices à couscous", "Épices à tajine", "Épices cajun", "Zaatar", "Sumac", "Mélange cinq baies",
    "Vanille", "Gousse de vanille", "Extrait de vanille", "Arôme vanille", "Sucre vanillé", "Réglisse",
    "Genièvre", "Baies de genièvre", "Ail en poudre", "Oignon en poudre", "Échalote séchée", "Oignons frits",
    # Herbes sèches
    "Herbes de Provence", "Thym séché", "Origan", "Origan séché", "Basilic séché", "Romarin séché",
    "Sauge séchée", "Laurier", "Feuille de laurier", "Estragon séché", "Persil séché", "Ciboulette séchée",
    "Aneth séché", "Menthe séchée", "Marjolaine", "Sarriette", "Bouquet garni", "Fines herbes",
    # Huiles et vinaigres
    "Huile", "Huile d'olive", "Huile de tournesol", "Huile de colza", "Huile de sésame", "Huile de noix",
    "Huile de noisette", "Huile de coco", "Huile d'arachide", "Huile de pépins de raisin", "Huile neutre",
    "Vinaigre", "Vinaigre balsamique", "Crème de balsamique", "Vinaigre de cidre", "Vinaigre de vin",
    "Vinaigre de vin blanc", "Vinaigre de vin rouge", "Vinaigre de Xérès", "Vinaigre de riz",
    "Vinaigre d'alcool", "Vinaigre blanc",
    # Condiments et sauces qui se gardent
    "Moutarde", "Moutarde à l'ancienne", "Moutarde douce", "Sauce soja", "Sauce soya", "Sauce soja sucrée",
    "Sauce Worcestershire", "Sauce nuoc-mâm", "Nuoc-mâm", "Sauce poisson", "Sauce huître", "Sauce hoisin",
    "Sauce Yakitori", "Sauce teriyaki", "Tabasco", "Sauce piquante", "Sriracha", "Harissa", "Sambal oelek",
    "Pâte de curry", "Pâte de curry rouge", "Pâte de curry vert", "Pâte de curry jaune", "Pâte d'arachide",
    "Beurre de cacahuète", "Tahini", "Purée de sésame", "Ketchup", "Mayonnaise", "Cornichons", "Câpres",
    "Olives", "Olives noires", "Olives vertes", "Tapenade", "Pesto", "Concentré de tomate",
    "Coulis de tomate", "Purée de tomate", "Passata", "Sauce tomate", "Tomates pelées en conserve",
    "Dés de tomates en conserve", "Tomates en conserve", "Tomates séchées", "Miso", "Mirin", "Saké",
    "Vin blanc", "Vin rouge", "Vin blanc de cuisine", "Apérol", "Prosecco", "Vodka", "Cognac", "Rhum",
    "Kirsch", "Porto", "Amaretto",
    # Bouillons et fonds
    "Bouillon", "Cube de bouillon", "Bouillon de volaille", "Bouillon de bœuf", "Bouillon de légumes",
    "Bouillon de poule", "Fond de veau", "Fumet de poisson",
    # Féculents
    "Pâtes", "Spaghetti", "Tagliatelles", "Penne", "Coquillettes", "Macaroni", "Lasagnes", "Nouilles",
    "Nouilles chinoises", "Nouilles de riz", "Vermicelles de riz", "Ramen", "Riz", "Riz basmati", "Riz thaï",
    "Riz rond", "Riz arborio", "Riz carnaroli", "Riz complet", "Riz sauvage", "Semoule", "Couscous",
    "Boulgour", "Quinoa", "Polenta", "Sarrasin", "Épeautre", "Orge perlé", "Flocons d'avoine", "Avoine",
    "Tapioca", "Chapelure", "Panko", "Croûtons", "Biscottes", "Gressins", "Crackers", "Pain azyme",
    "Tortillas", "Galettes de riz",
    # Légumineuses sèches ou en conserve
    "Lentilles", "Lentilles vertes", "Lentilles corail", "Lentilles blondes", "Pois chiches", "Pois cassés",
    "Haricots rouges", "Haricots blancs", "Haricots noirs", "Flageolets", "Fèves sèches",
    # Farines, sucres, pâtisserie
    "Farine", "Farine de blé", "Farine complète", "Farine de riz", "Farine de maïs", "Maïzena", "Fécule",
    "Fécule de maïs", "Fécule de pomme de terre", "Farine de sarrasin", "Farine de pois chiche",
    "Levure chimique", "Levure de boulanger", "Levure de boulanger sèche", "Bicarbonate", "Agar-agar",
    "Gélatine", "Sucre", "Sucre en poudre", "Sucre semoule", "Sucre glace", "Sucre roux", "Cassonade",
    "Vergeoise", "Sucre de canne", "Sucre complet", "Miel", "Sirop", "Sirop d'érable", "Sirop d'agave",
    "Mélasse", "Chocolat", "Chocolat noir", "Chocolat pâtissier", "Chocolat à cuire", "Chocolat au lait",
    "Chocolat blanc", "Pépites de chocolat", "Cacao", "Poudre de cacao", "Café", "Café soluble", "Thé",
    "Tisane", "Infusion", "Poudre d'amande", "Amandes en poudre", "Poudre de noisette", "Noix de coco râpée",
    "Pralin", "Pralinoise", "Pâte à tartiner", "Confiture", "Sirop de grenadine", "Grenadine",
    "Colorant alimentaire", "Vermicelles au chocolat", "Perles de sucre", "Boudoirs", "Biscuits",
    "Crêpes dentelle",
    # Fruits secs et graines
    "Amandes", "Noisettes", "Noix", "Noix de cajou", "Pistaches", "Cacahuètes", "Pignons de pin",
    "Noix de pécan", "Raisins secs", "Abricots secs", "Pruneaux", "Dattes", "Figues sèches",
    "Cranberries séchées", "Graines de sésame", "Sésame", "Graines de chia", "Graines de lin",
    "Graines de courge", "Graines de tournesol",
    # Conserves et lait longue conservation
    "Lait de coco", "Crème de coco", "Lait concentré", "Lait concentré sucré", "Lait en poudre",
    "Maïs en conserve", "Petits pois en conserve", "Thon en boîte", "Sardines en boîte",
    "Maquereaux en boîte", "Champignons en conserve", "Cœurs de palmier", "Cocktail de fruits",
    "Fruits au sirop",
    # Eau et boissons de cuisine
    "Eau", "Eau gazeuse",
)  # fmt: skip


# Mots seuls qui couvrent leurs variantes (« riz blanc », « cannelle en poudre »). Les autres
# mots seuls ne valent que pour eux-mêmes : « pâtes » ne doit pas couvrir « pâte feuilletée ».
_FAMILLES = frozenset(
    {"sel", "poivre", "huile", "vinaigre", "moutarde", "riz", "farine", "sucre", "bouillon", "lentille",
     "cafe", "the", "cannelle", "cumin", "curry", "curcuma", "paprika", "laurier", "bicarbonate", "miel",
     "crouton", "olive"}
)  # fmt: skip


@cache
def _cles() -> frozenset[str]:
    return frozenset(c for c in (cle(nom) for nom in PRODUITS_PLACARD) if c)


def propositions() -> dict[str, str]:
    """Produits de l'index par clé, dans l'ordre de la liste (le premier nom d'une clé l'emporte)."""
    produits: dict[str, str] = {}
    for nom in PRODUITS_PLACARD:
        if (c := cle(nom)) and c not in produits:
            produits[c] = nom
    return produits


# Tolérance aux fautes de frappe (« ras el anout ») : noms assez longs et très proches seulement.
LONGUEUR_MIN_APPROCHE = 8
SEUIL_APPROCHE = 0.9


def est_produit_de_placard(cle_produit: str) -> bool:
    """Vrai si le produit est un ingrédient de placard connu, une variante (« riz basmati bio »)
    ou une faute de frappe proche (« ras el anout »)."""
    if not cle_produit:
        return False
    cles = _cles()
    if cle_produit in cles:
        return True
    mots = cle_produit.split()
    # « huile olive vierge extra » commence par « huile olive » ; on essaie du plus long au plus court.
    if mots[0] in _FAMILLES or any(" ".join(mots[:n]) in cles for n in range(len(mots) - 1, 1, -1)):
        return True
    return len(cle_produit) >= LONGUEUR_MIN_APPROCHE and bool(
        get_close_matches(cle_produit, cles, n=1, cutoff=SEUIL_APPROCHE)
    )
