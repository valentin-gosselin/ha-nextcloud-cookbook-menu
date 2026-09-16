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
      </style>
      <ha-card><div id="contenu"></div><div class="menu" id="menu"></div></ha-card>`;
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
          <div class="texte"><div class="nom">${echapper(plat.summary)}</div><div class="detail">${echapper(detail)}</div></div>
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
    conteneur.querySelectorAll("button[data-retirer]").forEach((bouton) =>
      bouton.addEventListener("click", () =>
        this._hass.callService("todo", "remove_item", { entity_id: this._entiteMenu, item: [bouton.dataset.retirer] }),
      ),
    );
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
