/* Carte « Cookbook Menu » pour Home Assistant.
 *
 * Servie et enregistrée automatiquement par l'intégration cookbook_menu.
 *
 * Configuration :
 *   type: custom:cookbook-menu-card
 *   title: "Menu de la semaine"   (facultatif)
 *   config_entry_id: "..."        (facultatif, s'il y a plusieurs comptes)
 *
 * Recherche d'une recette pendant la frappe (sans tenir compte des accents), choix du jour et
 * des couverts, ajout au menu, puis affichage du menu avec « cuisiné » et suppression.
 */

const TEXTES = {
  fr: {
    titre: "Menu de la semaine",
    recherche: "Chercher une recette",
    aucune: "Aucune recette ne correspond",
    jour: "Jour",
    couverts: "Couverts",
    ajouter: "Ajouter au menu",
    choisir: "Choisissez une recette dans la liste",
    vide: "Rien au menu pour l'instant",
    sansDate: "Sans date",
    aujourdhui: "Aujourd'hui",
    demain: "Demain",
    jours: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    joursLongs: ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    pour: (n) => `${n} couvert${n > 1 ? "s" : ""}`,
    ajoute: (plat, n) =>
      `${plat} ajouté au menu` + (n ? `, ${n} ligne${n > 1 ? "s" : ""} de courses mise${n > 1 ? "s" : ""} à jour` : ""),
    retirer: "Retirer du menu",
    cuisine: "Cuisiné",
    nonConfigure: "Cookbook Menu n'est pas configuré",
    ouvrir: "Voir la recette",
    sansRecette: "Ce plat n'est lié à aucune recette",
    preparation: "Préparation",
    cuisson: "Cuisson",
    total: "Total",
    ingredients: "Ingrédients",
    etapes: "Étapes",
    ustensiles: "Ustensiles",
    fermer: "Fermer",
    source: "Recette d'origine",
    cookbook: "Ouvrir dans Cookbook",
    veille: "Garder l'écran allumé",
    veilleActive: "Écran maintenu allumé",
    minuteur: "Lancer un minuteur",
    termine: "Terminé",
    arreter: "Arrêter",
    facultatif: "facultatif",
  },
  en: {
    titre: "Weekly menu",
    recherche: "Search a recipe",
    aucune: "No matching recipe",
    jour: "Day",
    couverts: "Servings",
    ajouter: "Add to menu",
    choisir: "Pick a recipe from the list",
    vide: "Nothing on the menu yet",
    sansDate: "No date",
    aujourdhui: "Today",
    demain: "Tomorrow",
    jours: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    joursLongs: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    pour: (n) => `${n} serving${n > 1 ? "s" : ""}`,
    ajoute: (plat, n) => `${plat} added to the menu` + (n ? `, ${n} shopping item${n > 1 ? "s" : ""} updated` : ""),
    retirer: "Remove from menu",
    cuisine: "Cooked",
    nonConfigure: "Cookbook Menu is not set up",
    ouvrir: "Open the recipe",
    sansRecette: "This dish is not linked to a recipe",
    preparation: "Prep",
    cuisson: "Cook",
    total: "Total",
    ingredients: "Ingredients",
    etapes: "Steps",
    ustensiles: "Tools",
    fermer: "Close",
    source: "Original recipe",
    cookbook: "Open in Cookbook",
    veille: "Keep screen on",
    veilleActive: "Screen kept on",
    minuteur: "Start a timer",
    termine: "Done",
    arreter: "Stop",
    facultatif: "optional",
  },
};

function sansAccents(texte) {
  return (texte || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/œ/g, "oe")
    .toLowerCase();
}

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function duree(minutes) {
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
}

function chrono(secondes) {
  const s = Math.max(0, Math.round(secondes));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

const FRACTIONS = { 0.25: "¼", 0.5: "½", 0.75: "¾" };
const UNITES_CONTINUES = ["g", "kg", "mg", "ml", "cl", "dl", "l"];

function nombre(valeur, unite, langue) {
  let arrondi;
  if (UNITES_CONTINUES.includes(unite)) {
    arrondi = valeur >= 10 ? Math.round(valeur) : Math.round(valeur * 10) / 10;
    if (unite === "kg" || unite === "l") arrondi = Math.round(valeur * 100) / 100;
  } else if (valeur >= 2) {
    // On n'achète ni ne coupe « 3¼ carottes » : au-delà de 2, on arrondit à l'entier.
    arrondi = Math.round(valeur);
  } else {
    arrondi = Math.round(valeur * 4) / 4;
    if (arrondi === 0) arrondi = 0.25;
    const entier = Math.floor(arrondi);
    const reste = arrondi - entier;
    if (reste && FRACTIONS[reste]) return `${entier || ""}${FRACTIONS[reste]}`;
  }
  return String(arrondi).replace(".", langue === "fr" ? "," : ".");
}

function dateIso(date) {
  const decalage = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - decalage).toISOString().slice(0, 10);
}

class CookbookMenuCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._recettes = [];
    this._menu = [];
    this._requete = "";
    this._ouvert = false;
    this._surligne = 0;
    this._recette = null;
    this._jour = null; // null = sans date, sinon « AAAA-MM-JJ »
    this._couverts = null;
    this._message = "";
    this._erreur = "";
    this._chargement = null;
    this._desabonner = null;
    this._fiche = null;
    this._couvertsFiche = 2;
    this._etapesFaites = new Set();
    this._minuteurs = [];
    this._tic = null;
    this._verrou = null;
  }

  setConfig(config) {
    this._config = config || {};
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    const premier = !this._hass;
    this._hass = hass;
    if (premier) {
      this._rendreSquelette();
      this._charger();
    }
  }

  get _t() {
    const langue = (this._hass && this._hass.language) || "en";
    return TEXTES[langue.startsWith("fr") ? "fr" : "en"];
  }

  disconnectedCallback() {
    if (this._desabonner) {
      this._desabonner.then((fn) => fn && fn()).catch(() => {});
      this._desabonner = null;
    }
    this._chargement = null;
    if (this._tic) clearInterval(this._tic);
    this._tic = null;
    if (this._verrou) this._verrou.release().catch(() => {});
    this._verrou = null;
  }

  connectedCallback() {
    if (this._hass && !this._chargement) this._charger();
  }

  async _charger() {
    this._chargement = (async () => {
      try {
        const message = { type: "cookbook_menu/recipes" };
        if (this._config && this._config.config_entry_id) message.config_entry_id = this._config.config_entry_id;
        const reponse = await this._hass.callWS(message);
        this._entree = reponse.config_entry_id;
        this._recettes = reponse.recipes.map((r) => ({ ...r, cle: sansAccents(r.name) }));
        this._couverts = this._couverts || reponse.default_servings;
        this._entiteMenu = reponse.menu_entity;
        this._erreur = "";
        this._abonnerMenu();
      } catch (err) {
        this._erreur = this._t.nonConfigure;
      }
      this._rendre();
    })();
  }

  _abonnerMenu() {
    if (this._desabonner || !this._entiteMenu) return;
    this._desabonner = this._hass.connection.subscribeMessage(
      (evenement) => {
        this._menu = evenement.items || [];
        this._rendreMenu();
      },
      { type: "todo/item/subscribe", entity_id: this._entiteMenu },
    );
  }

  _filtrees() {
    const mots = sansAccents(this._requete).split(/\s+/).filter(Boolean);
    const liste = mots.length ? this._recettes.filter((r) => mots.every((m) => r.cle.includes(m))) : this._recettes;
    return liste.slice(0, 50);
  }

  _optionsJours() {
    const t = this._t;
    const aujourdhui = new Date();
    const options = [{ valeur: null, libelle: t.sansDate }];
    for (let i = 0; i < 7; i += 1) {
      const jour = new Date(aujourdhui);
      jour.setDate(aujourdhui.getDate() + i);
      const indice = (jour.getDay() + 6) % 7;
      const libelle = i === 0 ? t.aujourdhui : i === 1 ? t.demain : t.jours[indice];
      options.push({ valeur: dateIso(jour), libelle });
    }
    return options;
  }

  _rendreSquelette() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--primary-text-color); }
        ha-card { padding: 16px; }
        h2 { margin: 0 0 12px; font-size: 1.2em; font-weight: 500; color: var(--primary-text-color); }
        .recherche { position: relative; }
        input[type="search"] {
          width: 100%; box-sizing: border-box; padding: 10px 12px; font-size: 1em;
          border: 1px solid var(--divider-color); border-radius: 8px;
          background: var(--card-background-color); color: var(--primary-text-color);
        }
        input[type="search"]:focus { outline: 2px solid var(--primary-color); border-color: transparent; }
        .liste {
          position: absolute; z-index: 5; left: 0; right: 0; max-height: 260px; overflow-y: auto; margin-top: 4px;
          background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.2));
        }
        .choix { padding: 8px 12px; cursor: pointer; color: var(--primary-text-color); }
        .choix:hover { background: var(--secondary-background-color); }
        .choix.actif { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.25); }
        .choix.vide { cursor: default; color: var(--secondary-text-color); }
        .etiquette { margin: 12px 0 6px; font-size: .85em; color: var(--secondary-text-color); }
        .puces { display: flex; flex-wrap: wrap; gap: 6px; }
        .puce {
          border: 1px solid var(--divider-color); border-radius: 16px; padding: 4px 12px; cursor: pointer;
          background: transparent; color: var(--primary-text-color); font-size: .9em;
        }
        .puce.actif { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .ligne { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
        .compteur { display: flex; align-items: center; gap: 8px; }
        .compteur button {
          width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--divider-color);
          background: transparent; color: var(--primary-text-color); font-size: 1.1em; cursor: pointer;
        }
        .compteur #nombre { min-width: 24px; text-align: center; font-weight: 500; color: var(--primary-text-color); }
        .ajouter {
          border: none; border-radius: 8px; padding: 10px 16px; font-size: 1em; cursor: pointer;
          background: var(--primary-color); color: var(--text-primary-color, #fff);
        }
        .ajouter[disabled] { opacity: .5; cursor: default; }
        .message { margin-top: 8px; font-size: .9em; color: var(--secondary-text-color); min-height: 1.2em; }
        .erreur { color: var(--error-color); }
        .menu { margin-top: 16px; border-top: 1px solid var(--divider-color); padding-top: 8px; }
        .plat { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
        .plat .texte { flex: 1; min-width: 0; }
        .plat .nom { color: var(--primary-text-color); }
        .plat.fait .nom { text-decoration: line-through; color: var(--secondary-text-color); }
        .plat .detail { font-size: .85em; color: var(--secondary-text-color); }
        .plat button { background: transparent; border: none; cursor: pointer; color: var(--secondary-text-color); font-size: 1.1em; padding: 4px 8px; }
        .plat input { width: 18px; height: 18px; accent-color: var(--primary-color); }
        .vide { color: var(--secondary-text-color); font-size: .9em; padding: 6px 0; }
        .plat .texte { cursor: pointer; }
        .plat .texte:hover .nom { color: var(--primary-color); }
        .minuteurs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
        .minuteurs:empty { display: none; }
        .minuteur {
          display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 16px;
          background: var(--secondary-background-color); font-variant-numeric: tabular-nums;
        }
        .minuteur.fini { background: var(--error-color); color: #fff; animation: clignote 1s infinite; }
        .minuteur button { background: transparent; border: none; color: inherit; cursor: pointer; font-size: 1em; padding: 0 2px; }
        @keyframes clignote { 50% { opacity: .6; } }
        .voile {
          position: fixed; inset: 0; z-index: 10; background: rgba(0,0,0,.6);
          display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box;
        }
        .fenetre {
          background: var(--card-background-color); color: var(--primary-text-color); border-radius: 12px;
          width: 100%; max-width: 760px; max-height: 100%; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,.4);
        }
        @media (max-width: 600px) { .voile { padding: 0; } .fenetre { border-radius: 0; height: 100%; } }
        .entete { position: relative; }
        .entete img { width: 100%; max-height: 280px; object-fit: cover; display: block; border-radius: 12px 12px 0 0; }
        .fermer {
          position: absolute; top: 8px; right: 8px; width: 36px; height: 36px; border-radius: 50%; border: none;
          background: rgba(0,0,0,.55); color: #fff; font-size: 1.3em; cursor: pointer;
        }
        .corps { padding: 16px 20px 24px; }
        .corps h2 { margin: 0 0 6px; font-size: 1.5em; }
        .corps .description { color: var(--secondary-text-color); margin: 0 0 12px; line-height: 1.4; }
        .temps { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 12px; }
        .temps span { padding: 4px 10px; border-radius: 12px; background: var(--secondary-background-color); font-size: .9em; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
        .actions a, .actions button {
          border: 1px solid var(--divider-color); border-radius: 16px; padding: 4px 12px; font-size: .9em;
          color: var(--primary-text-color); background: transparent; text-decoration: none; cursor: pointer;
        }
        .actions button.actif { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .colonnes { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.6fr); gap: 24px; margin-top: 12px; }
        @media (max-width: 600px) { .colonnes { grid-template-columns: 1fr; } }
        .colonnes h3 { margin: 0 0 8px; font-size: 1.1em; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .ingredients { list-style: none; padding: 0; margin: 0; }
        .ingredients li { padding: 5px 0; border-bottom: 1px solid var(--divider-color); line-height: 1.35; }
        .ingredients li.section { border: none; font-weight: 500; padding-top: 12px; color: var(--secondary-text-color); }
        .ingredients .quantite { font-weight: 500; }
        .ingredients .note { color: var(--secondary-text-color); font-size: .9em; }
        .etapes { list-style: none; padding: 0; margin: 0; counter-reset: etape; }
        .etapes li {
          counter-increment: etape; display: grid; grid-template-columns: 32px 1fr; gap: 8px; padding: 8px 0;
          border-bottom: 1px solid var(--divider-color); cursor: pointer; line-height: 1.45;
        }
        .etapes li::before {
          content: counter(etape); width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
          background: var(--primary-color); color: var(--text-primary-color, #fff); font-size: .85em; font-weight: 500;
        }
        .etapes li.faite { opacity: .45; }
        .etapes li.faite::before { content: "\\2713"; background: var(--secondary-text-color); }
        .lancer {
          border: 1px solid var(--primary-color); color: var(--primary-color); background: transparent;
          border-radius: 12px; padding: 0 8px; font: inherit; cursor: pointer; white-space: nowrap;
        }
        .ustensiles { margin-top: 16px; color: var(--secondary-text-color); font-size: .9em; }
      </style>
      <ha-card><div id="contenu"></div><div class="minuteurs" id="minuteurs"></div><div class="menu" id="menu"></div></ha-card>
      <div id="fenetre"></div>`;
  }

  _rendre() {
    const t = this._t;
    const contenu = this.shadowRoot.getElementById("contenu");
    if (!contenu) return;
    if (this._erreur) {
      contenu.innerHTML = `<h2>${echapper(this._config.title || t.titre)}</h2><div class="message erreur">${echapper(this._erreur)}</div>`;
      return;
    }
    const jours = this._optionsJours()
      .map((o) => `<button class="puce ${o.valeur === this._jour ? "actif" : ""}" data-jour="${o.valeur ?? ""}">${echapper(o.libelle)}</button>`)
      .join("");
    contenu.innerHTML = `
      <h2>${echapper(this._config.title || t.titre)}</h2>
      <div class="recherche">
        <input type="search" id="saisie" placeholder="${echapper(t.recherche)}" autocomplete="off"
               value="${echapper(this._recette ? this._recette.name : this._requete)}">
        <div class="liste" id="liste" hidden></div>
      </div>
      <div class="etiquette">${echapper(t.jour)}</div>
      <div class="puces">${jours}</div>
      <div class="ligne">
        <div class="compteur">
          <span class="etiquette" style="margin:0">${echapper(t.couverts)}</span>
          <button id="moins" aria-label="-">&minus;</button><span id="nombre">${this._couverts || 2}</span><button id="plus" aria-label="+">+</button>
        </div>
        <button class="ajouter" id="ajouter" ${this._recette ? "" : "disabled"}>${echapper(t.ajouter)}</button>
      </div>
      <div class="message" id="message">${echapper(this._message)}</div>`;
    this._brancher();
    this._rendreMenu();
  }

  _brancher() {
    const saisie = this.shadowRoot.getElementById("saisie");
    saisie.addEventListener("input", () => {
      this._requete = saisie.value;
      this._recette = null;
      this._surligne = 0;
      this._ouvrirListe();
      this.shadowRoot.getElementById("ajouter").disabled = true;
    });
    saisie.addEventListener("focus", () => this._ouvrirListe());
    saisie.addEventListener("blur", () => setTimeout(() => this._fermerListe(), 150));
    saisie.addEventListener("keydown", (e) => {
      const filtrees = this._filtrees();
      if (e.key === "ArrowDown") {
        this._surligne = Math.min(this._surligne + 1, filtrees.length - 1);
        this._ouvrirListe();
        e.preventDefault();
      } else if (e.key === "ArrowUp") {
        this._surligne = Math.max(this._surligne - 1, 0);
        this._ouvrirListe();
        e.preventDefault();
      } else if (e.key === "Enter") {
        if (this._recette) this._ajouter();
        else if (filtrees[this._surligne]) this._choisir(filtrees[this._surligne]);
        e.preventDefault();
      } else if (e.key === "Escape") {
        this._fermerListe();
      }
    });
    this.shadowRoot.querySelectorAll(".puce").forEach((puce) =>
      puce.addEventListener("click", () => {
        this._jour = puce.dataset.jour || null;
        this.shadowRoot.querySelectorAll(".puce").forEach((p) => p.classList.toggle("actif", p === puce));
      }),
    );
    this.shadowRoot.getElementById("moins").addEventListener("click", () => this._changerCouverts(-1));
    this.shadowRoot.getElementById("plus").addEventListener("click", () => this._changerCouverts(1));
    this.shadowRoot.getElementById("ajouter").addEventListener("click", () => this._ajouter());
  }

  _ouvrirListe() {
    const liste = this.shadowRoot.getElementById("liste");
    const filtrees = this._filtrees();
    liste.innerHTML = filtrees.length
      ? filtrees
          .map((r, i) => `<div class="choix ${i === this._surligne ? "actif" : ""}" data-id="${echapper(r.id)}">${echapper(r.name)}</div>`)
          .join("")
      : `<div class="choix vide">${echapper(this._t.aucune)}</div>`;
    liste.hidden = false;
    liste.querySelectorAll(".choix[data-id]").forEach((element) =>
      element.addEventListener("mousedown", (e) => {
        e.preventDefault();
        this._choisir(this._recettes.find((r) => r.id === element.dataset.id));
      }),
    );
    const actif = liste.querySelector(".choix.actif");
    if (actif) actif.scrollIntoView({ block: "nearest" });
  }

  _fermerListe() {
    const liste = this.shadowRoot.getElementById("liste");
    if (liste) liste.hidden = true;
  }

  _choisir(recette) {
    if (!recette) return;
    this._recette = recette;
    this._requete = recette.name;
    const saisie = this.shadowRoot.getElementById("saisie");
    saisie.value = recette.name;
    this._fermerListe();
    this.shadowRoot.getElementById("ajouter").disabled = false;
  }

  _changerCouverts(ecart) {
    this._couverts = Math.max(1, Math.min(30, (this._couverts || 2) + ecart));
    this.shadowRoot.getElementById("nombre").textContent = this._couverts;
  }

  async _ajouter() {
    if (!this._recette) {
      this._afficherMessage(this._t.choisir, true);
      return;
    }
    const donnees = { recipe: this._recette.name, recipe_id: this._recette.id, servings: this._couverts };
    if (this._jour) donnees.day = this._jour;
    if (this._entree) donnees.config_entry_id = this._entree;
    try {
      const resultat = await this._hass.callWS({
        type: "call_service",
        domain: "cookbook_menu",
        service: "add_to_menu",
        service_data: donnees,
        return_response: true,
      });
      const bilan = (resultat && resultat.response) || {};
      this._afficherMessage(this._t.ajoute(bilan.dish || this._recette.name, (bilan.shopping_items_changed || []).length));
      this._recette = null;
      this._requete = "";
      const saisie = this.shadowRoot.getElementById("saisie");
      saisie.value = "";
      this.shadowRoot.getElementById("ajouter").disabled = true;
    } catch (err) {
      this._afficherMessage((err && err.message) || String(err), true);
    }
  }

  _afficherMessage(texte, erreur = false) {
    this._message = texte;
    const message = this.shadowRoot.getElementById("message");
    if (message) {
      message.textContent = texte;
      message.classList.toggle("erreur", erreur);
    }
  }

  _rendreMenu() {
    const conteneur = this.shadowRoot.getElementById("menu");
    if (!conteneur || this._erreur) return;
    const t = this._t;
    if (!this._menu.length) {
      conteneur.innerHTML = `<div class="vide">${echapper(t.vide)}</div>`;
      return;
    }
    conteneur.innerHTML = this._menu
      .map((plat) => {
        let jour = "";
        if (plat.due) {
          const date = new Date(`${plat.due}T12:00:00`);
          jour = t.joursLongs[(date.getDay() + 6) % 7];
          jour = jour.charAt(0).toUpperCase() + jour.slice(1);
        }
        const detail = [jour, plat.description].filter(Boolean).join(", ");
        const fait = plat.status === "completed";
        return `<div class="plat ${fait ? "fait" : ""}">
          <input type="checkbox" title="${echapper(t.cuisine)}" data-uid="${echapper(plat.uid)}" ${fait ? "checked" : ""}>
          <div class="texte" role="button" tabindex="0" title="${echapper(t.ouvrir)}" data-ouvrir="${echapper(plat.uid)}"><div class="nom">${echapper(plat.summary)}</div><div class="detail">${echapper(detail)}</div></div>
          <button title="${echapper(t.retirer)}" aria-label="${echapper(t.retirer)}" data-retirer="${echapper(plat.uid)}">&times;</button>
        </div>`;
      })
      .join("");
    conteneur.querySelectorAll("input[data-uid]").forEach((caseACocher) =>
      caseACocher.addEventListener("change", () =>
        this._hass.callService("todo", "update_item", {
          entity_id: this._entiteMenu,
          item: caseACocher.dataset.uid,
          status: caseACocher.checked ? "completed" : "needs_action",
        }),
      ),
    );
    conteneur.querySelectorAll("[data-ouvrir]").forEach((element) => {
      element.addEventListener("click", () => this._ouvrirFiche(element.dataset.ouvrir));
      element.addEventListener("keydown", (e) => e.key === "Enter" && this._ouvrirFiche(element.dataset.ouvrir));
    });
    conteneur.querySelectorAll("button[data-retirer]").forEach((bouton) =>
      bouton.addEventListener("click", () =>
        this._hass.callService("todo", "remove_item", { entity_id: this._entiteMenu, item: [bouton.dataset.retirer] }),
      ),
    );
  }
  async _ouvrirFiche(uid) {
    try {
      const message = { type: "cookbook_menu/recipe", uid };
      if (this._entree) message.config_entry_id = this._entree;
      this._fiche = await this._hass.callWS(message);
    } catch (err) {
      this._afficherMessage(this._t.sansRecette, true);
      return;
    }
    this._couvertsFiche = this._fiche.servings;
    this._etapesFaites = new Set();
    this._rendreFiche();
  }

  _fermerFiche() {
    this._fiche = null;
    this.shadowRoot.getElementById("fenetre").innerHTML = "";
    document.removeEventListener("keydown", this._echap);
  }

  _ligneIngredient(ligne) {
    const t = this._t;
    const langue = (this._hass.language || "en").startsWith("fr") ? "fr" : "en";
    if (ligne.section) return `<li class="section">${echapper(ligne.section)}</li>`;
    const facteur = this._couvertsFiche / (this._fiche.yield || 1);
    let quantite = "";
    if (ligne.quantity) {
      quantite = nombre(ligne.quantity * facteur, ligne.unit, langue);
      if (ligne.quantity_max) quantite += `-${nombre(ligne.quantity_max * facteur, ligne.unit, langue)}`;
      if (ligne.unit) quantite += ` ${ligne.unit}`;
    } else if (ligne.vague) {
      quantite = ligne.vague;
    }
    const notes = [ligne.note, ligne.optional && !String(ligne.note || "").includes(t.facultatif) ? t.facultatif : ""].filter(Boolean).join(", ");
    return `<li>${quantite ? `<span class="quantite">${echapper(quantite)}</span> ` : ""}${echapper(ligne.name)}${notes ? ` <span class="note">(${echapper(notes)})</span>` : ""}</li>`;
  }

  _etape(etape, indice) {
    let html = "";
    let position = 0;
    for (const minuteur of etape.timers) {
      html += echapper(etape.text.slice(position, minuteur.start));
      html += `<button class="lancer" title="${echapper(this._t.minuteur)}" data-secondes="${minuteur.seconds}" data-libelle="${echapper(minuteur.text)}">${echapper(minuteur.text)}</button>`;
      position = minuteur.end;
    }
    html += echapper(etape.text.slice(position));
    return `<li class="${this._etapesFaites.has(indice) ? "faite" : ""}" data-etape="${indice}"><span>${html}</span></li>`;
  }

  _rendreFiche() {
    const f = this._fiche;
    const t = this._t;
    if (!f) return;
    const temps = [
      f.prep_minutes && `${t.preparation} ${duree(f.prep_minutes)}`,
      f.cook_minutes && `${t.cuisson} ${duree(f.cook_minutes)}`,
      f.total_minutes && `${t.total} ${duree(f.total_minutes)}`,
    ].filter(Boolean);
    const fenetre = this.shadowRoot.getElementById("fenetre");
    fenetre.innerHTML = `
      <div class="voile" id="voile">
        <div class="fenetre" role="dialog" aria-modal="true" aria-label="${echapper(f.name)}">
          <div class="entete">
            <img id="photo" src="${echapper(f.image)}" alt="" hidden>
            <button class="fermer" id="fermer" aria-label="${echapper(t.fermer)}">&times;</button>
          </div>
          <div class="corps">
            <h2>${echapper(f.name)}</h2>
            ${f.description ? `<p class="description">${echapper(f.description)}</p>` : ""}
            ${temps.length ? `<div class="temps">${temps.map((x) => `<span>${echapper(x)}</span>`).join("")}</div>` : ""}
            <div class="actions">
              <button id="veille" class="${this._verrou ? "actif" : ""}">${echapper(this._verrou ? t.veilleActive : t.veille)}</button>
              ${f.cookbook_url ? `<a href="${echapper(f.cookbook_url)}" target="_blank" rel="noopener">${echapper(t.cookbook)}</a>` : ""}
              ${f.url ? `<a href="${echapper(f.url)}" target="_blank" rel="noopener">${echapper(t.source)}</a>` : ""}
            </div>
            <div class="colonnes">
              <div>
                <h3>${echapper(t.ingredients)}
                  <span class="compteur">
                    <button id="fiche-moins" aria-label="-">&minus;</button><span id="nombre">${this._couvertsFiche}</span><button id="fiche-plus" aria-label="+">+</button>
                  </span>
                </h3>
                <ul class="ingredients" id="ingredients">${f.ingredients.map((l) => this._ligneIngredient(l)).join("")}</ul>
                ${f.tools.length ? `<div class="ustensiles">${echapper(t.ustensiles)} : ${echapper(f.tools.join(", "))}</div>` : ""}
              </div>
              <div>
                <h3>${echapper(t.etapes)}</h3>
                <ol class="etapes" id="etapes">${f.steps.map((e, i) => this._etape(e, i)).join("")}</ol>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    const photo = this.shadowRoot.getElementById("photo");
    photo.addEventListener("load", () => (photo.hidden = false));
    photo.addEventListener("error", () => photo.remove());
    this.shadowRoot.getElementById("fermer").addEventListener("click", () => this._fermerFiche());
    this.shadowRoot.getElementById("voile").addEventListener("click", (e) => e.target.id === "voile" && this._fermerFiche());
    this._echap = (e) => e.key === "Escape" && this._fermerFiche();
    document.addEventListener("keydown", this._echap);
    this.shadowRoot.getElementById("veille").addEventListener("click", () => this._basculerVeille());
    const changer = (ecart) => {
      this._couvertsFiche = Math.max(1, Math.min(50, this._couvertsFiche + ecart));
      this.shadowRoot.querySelector(".fenetre #nombre").textContent = this._couvertsFiche;
      this.shadowRoot.getElementById("ingredients").innerHTML = f.ingredients.map((l) => this._ligneIngredient(l)).join("");
    };
    this.shadowRoot.getElementById("fiche-moins").addEventListener("click", () => changer(-1));
    this.shadowRoot.getElementById("fiche-plus").addEventListener("click", () => changer(1));
    this.shadowRoot.getElementById("etapes").addEventListener("click", (e) => {
      const bouton = e.target.closest(".lancer");
      if (bouton) {
        e.stopPropagation();
        this._lancerMinuteur(Number(bouton.dataset.secondes), `${f.name} : ${bouton.dataset.libelle}`);
        return;
      }
      const li = e.target.closest("li[data-etape]");
      if (!li) return;
      const indice = Number(li.dataset.etape);
      if (this._etapesFaites.has(indice)) this._etapesFaites.delete(indice);
      else this._etapesFaites.add(indice);
      li.classList.toggle("faite");
    });
  }

  async _basculerVeille() {
    const t = this._t;
    const bouton = this.shadowRoot.getElementById("veille");
    try {
      if (this._verrou) {
        await this._verrou.release();
        this._verrou = null;
      } else if (navigator.wakeLock) {
        this._verrou = await navigator.wakeLock.request("screen");
        this._verrou.addEventListener("release", () => (this._verrou = null));
      }
    } catch (err) {
      this._verrou = null;
    }
    if (bouton) {
      bouton.classList.toggle("actif", Boolean(this._verrou));
      bouton.textContent = this._verrou ? t.veilleActive : t.veille;
    }
  }

  _lancerMinuteur(secondes, libelle) {
    this._minuteurs.push({ id: Date.now() + Math.random(), libelle, fin: Date.now() + secondes * 1000, sonne: false });
    if (!this._tic) this._tic = setInterval(() => this._rendreMinuteurs(), 1000);
    this._rendreMinuteurs();
  }

  _rendreMinuteurs() {
    const conteneur = this.shadowRoot.getElementById("minuteurs");
    if (!conteneur) return;
    const t = this._t;
    const maintenant = Date.now();
    conteneur.innerHTML = this._minuteurs
      .map((m) => {
        const restant = (m.fin - maintenant) / 1000;
        if (restant <= 0 && !m.sonne) {
          m.sonne = true;
          this._sonner();
        }
        const fini = restant <= 0;
        return `<div class="minuteur ${fini ? "fini" : ""}"><span>${echapper(m.libelle)}</span><strong>${fini ? echapper(t.termine) : chrono(restant)}</strong><button data-arreter="${m.id}" title="${echapper(t.arreter)}" aria-label="${echapper(t.arreter)}">&times;</button></div>`;
      })
      .join("");
    conteneur.querySelectorAll("button[data-arreter]").forEach((bouton) =>
      bouton.addEventListener("click", () => {
        this._minuteurs = this._minuteurs.filter((m) => String(m.id) !== bouton.dataset.arreter);
        this._rendreMinuteurs();
      }),
    );
    if (!this._minuteurs.length && this._tic) {
      clearInterval(this._tic);
      this._tic = null;
    }
  }

  _sonner() {
    try {
      const contexte = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.4, 0.8].forEach((decalage) => {
        const oscillateur = contexte.createOscillator();
        const volume = contexte.createGain();
        oscillateur.frequency.value = 880;
        volume.gain.value = 0.25;
        oscillateur.connect(volume).connect(contexte.destination);
        oscillateur.start(contexte.currentTime + decalage);
        oscillateur.stop(contexte.currentTime + decalage + 0.25);
      });
    } catch (err) {
      /* son indisponible : le clignotement suffit */
    }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  }
}


const TEXTES_RESERVE = {
  fr: {
    titre: "Réserve",
    verifier: "Première vérification du placard",
    verifierAide: "Tout est considéré comme présent. Décochez ce qui manque, puis validez.",
    valider: "Valider",
    aRacheter: "À racheter",
    rien: "Rien à racheter",
    placard: "Placard",
    placardAide: "Touchez un produit quand il n'y en a plus.",
    frigo: "Frigo",
    frigoVide: "Rien d'acheté pour le menu en ce moment",
    maison: "Maison",
    maisonVide: "Les achats hors menu apparaîtront ici une fois cochés dans la liste de courses",
    jours: (n) => (n <= 0 ? "à consommer aujourd'hui" : `encore ${n} jour${n > 1 ? "s" : ""}`),
    plusRien: "Il n'y en a plus",
    jEnAi: "J'en ai",
    sortir: "Sortir de la réserve",
    nonConfigure: "Cookbook Menu n'est pas configuré",
  },
  en: {
    titre: "Stock",
    verifier: "First pantry check",
    verifierAide: "Everything is considered in stock. Uncheck what is missing, then confirm.",
    valider: "Confirm",
    aRacheter: "To buy again",
    rien: "Nothing to buy again",
    placard: "Pantry",
    placardAide: "Tap a product when you run out of it.",
    frigo: "Fridge",
    frigoVide: "Nothing bought for the menu right now",
    maison: "Household",
    maisonVide: "Items bought outside the menu show up here once checked on the shopping list",
    jours: (n) => (n <= 0 ? "use today" : `${n} day${n > 1 ? "s" : ""} left`),
    plusRien: "Out of stock",
    jEnAi: "In stock",
    sortir: "Remove from stock",
    nonConfigure: "Cookbook Menu is not set up",
  },
};

class CookbookStockCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._reserve = null;
    this._manquantsVerification = new Set();
    this._desabonner = null;
    this._erreur = "";
  }

  setConfig(config) {
    this._config = config || {};
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 5;
  }

  get _t() {
    const langue = (this._hass && this._hass.language) || "en";
    return TEXTES_RESERVE[langue.startsWith("fr") ? "fr" : "en"];
  }

  set hass(hass) {
    const premier = !this._hass;
    this._hass = hass;
    if (premier) this._abonner();
  }

  connectedCallback() {
    if (this._hass && !this._desabonner) this._abonner();
  }

  disconnectedCallback() {
    if (this._desabonner) {
      this._desabonner.then((fn) => fn && fn()).catch(() => {});
      this._desabonner = null;
    }
  }

  _abonner() {
    const message = { type: "cookbook_menu/stock/subscribe" };
    if (this._config && this._config.config_entry_id) message.config_entry_id = this._config.config_entry_id;
    this._desabonner = this._hass.connection.subscribeMessage((reserve) => {
      this._reserve = reserve;
      this._erreur = "";
      this._rendre();
    }, message);
    this._desabonner.catch(() => {
      this._erreur = this._t.nonConfigure;
      this._rendre();
    });
  }

  _agir(action, cle, extra = {}) {
    const message = { type: "cookbook_menu/stock/update", action, ...extra };
    if (cle) message.key = cle;
    if (this._config && this._config.config_entry_id) message.config_entry_id = this._config.config_entry_id;
    return this._hass.callWS(message);
  }

  _rendre() {
    const t = this._t;
    const r = this._reserve;
    const style = `
      <style>
        :host { display: block; color: var(--primary-text-color); }
        ha-card { padding: 16px; }
        h2 { margin: 0 0 8px; font-size: 1.2em; font-weight: 500; }
        h3 { margin: 16px 0 6px; font-size: 1em; font-weight: 500; display: flex; align-items: baseline; gap: 8px; }
        h3 small { font-weight: 400; color: var(--secondary-text-color); font-size: .8em; }
        .aide, .vide { color: var(--secondary-text-color); font-size: .9em; }
        .puces { display: flex; flex-wrap: wrap; gap: 6px; }
        .puce {
          border: 1px solid var(--divider-color); border-radius: 16px; padding: 4px 12px; cursor: pointer;
          background: transparent; color: var(--primary-text-color); font-size: .9em;
        }
        .puce.manque { border-color: var(--error-color); color: var(--error-color); }
        .verification { border: 1px solid var(--primary-color); border-radius: 12px; padding: 12px; margin-bottom: 8px; }
        .verification label { display: inline-flex; align-items: center; gap: 4px; margin: 4px 12px 4px 0; }
        .ligne { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--divider-color); flex-wrap: wrap; }
        .ligne .nom { flex: 1; min-width: 120px; }
        .ligne .detail { color: var(--secondary-text-color); font-size: .85em; }
        .ligne .detail.urgent { color: var(--error-color); }
        button.action {
          border: 1px solid var(--divider-color); border-radius: 12px; background: transparent; cursor: pointer;
          color: var(--primary-text-color); padding: 2px 10px; font-size: .85em;
        }
        button.principal { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
      </style>`;
    if (this._erreur || !r) {
      this.shadowRoot.innerHTML = `${style}<ha-card><h2>${echapper(this._config.title || t.titre)}</h2><div class="aide">${echapper(this._erreur)}</div></ha-card>`;
      return;
    }
    const aRacheter = [
      ...r.pantry.filter((p) => p.missing).map((p) => ({ cle: p.key, nom: p.name })),
      ...r.home.filter((m) => !m.present).map((m) => ({ cle: m.key, nom: m.name })),
    ];
    const verification = r.pantry_checked
      ? ""
      : `<div class="verification"><strong>${echapper(t.verifier)}</strong><div class="aide">${echapper(t.verifierAide)}</div>
          <div>${r.pantry
            .map((p) => `<label><input type="checkbox" data-verifier="${echapper(p.key)}" ${this._manquantsVerification.has(p.key) ? "" : "checked"}> ${echapper(p.name)}</label>`)
            .join("")}</div>
          <button class="action principal" id="valider">${echapper(t.valider)}</button></div>`;
    this.shadowRoot.innerHTML = `${style}<ha-card>
      <h2>${echapper(this._config.title || t.titre)}</h2>
      ${verification}
      <h3>${echapper(t.aRacheter)}</h3>
      ${aRacheter.length
        ? `<div class="puces">${aRacheter.map((p) => `<button class="puce manque" data-present="${echapper(p.cle)}" title="${echapper(t.jEnAi)}">${echapper(p.nom)}</button>`).join("")}</div>`
        : `<div class="vide">${echapper(t.rien)}</div>`}
      <h3>${echapper(t.frigo)}</h3>
      ${r.fridge.length
        ? r.fridge
            .map(
              (f) => `<div class="ligne"><span class="nom">${echapper(f.name)}${f.quantity ? ` <span class="detail">(${echapper(f.quantity)})</span>` : ""}</span>
                <span class="detail ${f.days_left !== null && f.days_left <= 1 ? "urgent" : ""}">${f.days_left === null ? "" : echapper(t.jours(f.days_left))}</span>
                <button class="action" data-manquant="${echapper(f.key)}">${echapper(t.plusRien)}</button></div>`,
            )
            .join("")
        : `<div class="vide">${echapper(t.frigoVide)}</div>`}
      <h3>${echapper(t.placard)} <small>${echapper(t.placardAide)}</small></h3>
      <div class="puces">${r.pantry
        .filter((p) => !p.missing)
        .map((p) => `<button class="puce" data-manquant="${echapper(p.key)}" title="${echapper(t.plusRien)}">${echapper(p.name)}</button>`)
        .join("")}</div>
      <h3>${echapper(t.maison)}</h3>
      ${r.home.some((m) => m.present)
        ? r.home
            .filter((m) => m.present)
            .map(
              (m) => `<div class="ligne"><span class="nom">${echapper(m.name)}${m.description ? ` <span class="detail">${echapper(m.description)}</span>` : ""}</span>
                <button class="action" data-manquant="${echapper(m.key)}">${echapper(t.plusRien)}</button>
                <button class="action" data-retirer="${echapper(m.key)}">${echapper(t.sortir)}</button></div>`,
            )
            .join("")
        : `<div class="vide">${echapper(t.maisonVide)}</div>`}
    </ha-card>`;
    this.shadowRoot.querySelectorAll("[data-present]").forEach((b) => b.addEventListener("click", () => this._agir("present", b.dataset.present)));
    this.shadowRoot.querySelectorAll("[data-manquant]").forEach((b) => b.addEventListener("click", () => this._agir("missing", b.dataset.manquant)));
    this.shadowRoot.querySelectorAll("[data-retirer]").forEach((b) => b.addEventListener("click", () => this._agir("remove", b.dataset.retirer)));
    this.shadowRoot.querySelectorAll("[data-verifier]").forEach((c) =>
      c.addEventListener("change", () => {
        if (c.checked) this._manquantsVerification.delete(c.dataset.verifier);
        else this._manquantsVerification.add(c.dataset.verifier);
      }),
    );
    const valider = this.shadowRoot.getElementById("valider");
    if (valider) valider.addEventListener("click", () => this._agir("check_pantry", null, { missing: [...this._manquantsVerification] }));
  }
}

if (!customElements.get("cookbook-menu-card")) {
  customElements.define("cookbook-menu-card", CookbookMenuCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "cookbook-menu-card",
    name: "Cookbook Menu",
    description: "Weekly menu from Nextcloud Cookbook recipes, with recipe search.",
    preview: false,
  });
}

if (!customElements.get("cookbook-stock-card")) {
  customElements.define("cookbook-stock-card", CookbookStockCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "cookbook-stock-card",
    name: "Cookbook Menu : réserve",
    description: "Pantry, fridge and household stock kept up to date from the menu and the shopping list.",
    preview: false,
  });
}
