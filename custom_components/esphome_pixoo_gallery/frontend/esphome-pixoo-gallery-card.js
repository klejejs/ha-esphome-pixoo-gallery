// ESPHome Pixoo Gallery card: paste, drop or pick an image/GIF, paste a link, or type a
// scrolling text, and show it on the Pixoo.  type: custom:esphome-pixoo-gallery-card
// entry_id: <config entry> (optional, the first display when left out)
const DOMAIN = "esphome_pixoo_gallery";
const TILE_CSS = `
  .history { display: grid; grid-template-columns: repeat(auto-fill, minmax(52px, 1fr)); gap: 6px; }
  .history button {
    padding: 0; aspect-ratio: 1; border-radius: 6px; overflow: hidden; background: #000;
    border: 2px solid transparent; cursor: pointer;
    -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; touch-action: manipulation;
  }
  .history button.current { border-color: var(--primary-color); }
  .history button.held { transform: scale(.92); transition: transform .2s; }
  .history img { width: 100%; height: 100%; display: block; image-rendering: pixelated; pointer-events: none; }
  .history .text {
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4; text-align: center;
    font: bold 10px/1.15 sans-serif; overflow: hidden; overflow-wrap: anywhere; margin: 4px 2px;
  }
`;
const HOLD_MS = 550;

// The finger that held a tile is still down when a popup opens, so its release must not
// count as a tap on the popup: only a press that starts on the element itself does.
function onTap(el, handler) {
  let armed = false;
  el.addEventListener("pointerdown", () => { armed = true; });
  el.addEventListener("click", (e) => { if (armed) handler(e); armed = false; });
}

class PixooGalleryCard extends HTMLElement {
  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { ...config };
    if (!this.shadowRoot) this._build();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._display) {
      this._connect();
      return;
    }
    // The image entity changes whenever any device shows something new.
    const state = this._display.image_entity && hass.states[this._display.image_entity];
    const picture = state && state.attributes.entity_picture;
    const stamp = picture ? `${picture}&v=${state.state}` : null;
    if (stamp !== this._picture) {
      this._picture = stamp;
      this._refreshPreview();
    }
  }

  async _connect() {
    if (this._connecting || !this._hass || Date.now() < (this._retryAt || 0)) return;
    this._connecting = true;
    this._retryAt = Date.now() + 30000;
    try {
      const displays = await this._hass.callWS({ type: `${DOMAIN}/displays` });
      const display = this._config.entry_id
        ? displays.find((d) => d.entry_id === this._config.entry_id)
        : displays[0];
      if (!display) {
        this._setStatus("No Pixoo display is set up. Add one under Settings → Devices & services.", true);
        return;
      }
      this._display = display;
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        (msg) => this._setHistory(msg.history, msg.current),
        { type: `${DOMAIN}/subscribe`, entry_id: display.entry_id },
      );
      this.hass = this._hass;
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    } finally {
      this._connecting = false;
    }
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  connectedCallback() {
    this._onPaste = (e) => this._handlePaste(e);
    window.addEventListener("paste", this._onPaste);
    if (this._hass && !this._display) this._connect();
  }

  disconnectedCallback() {
    window.removeEventListener("paste", this._onPaste);
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    this._display = null;
    this._picture = undefined;
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        ha-card { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
        .drop {
          position: relative; border: 2px dashed var(--divider-color); border-radius: 12px;
          aspect-ratio: 1; max-width: 256px; width: 100%; margin: 0 auto; cursor: pointer;
          display: flex; align-items: center; justify-content: center; overflow: hidden;
          background: #000;
        }
        .drop.over { border-color: var(--primary-color); }
        .drop img { width: 100%; height: 100%; image-rendering: pixelated; }
        .drop .hint {
          position: absolute; color: #fff; text-align: center; font-size: 14px; padding: 8px;
          background: rgba(0,0,0,.55); border-radius: 8px; pointer-events: none;
        }
        .row { display: flex; gap: 8px; }
        input[type=text] {
          flex: 1; min-width: 0; font: inherit; padding: 8px 10px; border-radius: 8px;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        button {
          font: inherit; padding: 8px 14px; border-radius: 8px; border: 0; cursor: pointer;
          background: var(--primary-color); color: var(--text-primary-color, #fff);
        }
        button:disabled { opacity: .5; cursor: default; }
        .status { font-size: 13px; color: var(--secondary-text-color); min-height: 1em; text-align: center; }
        .status.error { color: var(--error-color); }
        ${TILE_CSS}
        .history button.overflow { display: none; }
        .label { font-size: 13px; color: var(--secondary-text-color); display: flex; justify-content: space-between; align-items: center; }
        .label[hidden] { display: none; }
        .label button.all {
          background: none; color: var(--primary-color); padding: 0; font-size: 13px; border-radius: 0;
        }
        input[type=color] {
          width: 40px; height: 38px; padding: 2px; border-radius: 8px; cursor: pointer; flex: none;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
        }
      </style>
      <ha-card>
        <div class="drop" tabindex="0">
          <img alt="">
          <div class="hint">Paste, drop or tap<br>to choose an image or GIF</div>
        </div>
        <input type="file" accept="image/*" hidden>
        <div class="row">
          <input type="text" class="link" placeholder="…or paste a link" inputmode="url">
          <button class="show-link">Show</button>
        </div>
        <div class="row">
          <input type="text" class="message" placeholder="Type a text to scroll" maxlength="120" enterkeyhint="send">
          <input type="color" title="Text colour">
          <button class="show-text">Show</button>
        </div>
        <div class="status"></div>
        <div class="label" hidden><span>Earlier · hold to remove</span><button class="all" hidden>Show all</button></div>
        <div class="history"></div>
      </ha-card>`;
    this._drop = root.querySelector(".drop");
    this._img = root.querySelector("img");
    this._hint = root.querySelector(".hint");
    this._file = root.querySelector("input[type=file]");
    this._url = root.querySelector("input.link");
    this._button = root.querySelector("button.show-link");
    this._message = root.querySelector("input.message");
    this._color = root.querySelector("input[type=color]");
    this._textButton = root.querySelector("button.show-text");
    try { this._color.value = localStorage.getItem("esphome-pixoo-gallery-color") || "#ffaa00"; } catch (err) { this._color.value = "#ffaa00"; }
    this._history = root.querySelector(".history");
    this._historyLabel = root.querySelector(".label");
    this._allButton = root.querySelector("button.all");
    this._allButton.addEventListener("click", () => this._openAll());
    this._items = [];
    this._current = null;
    this._thumbs = new Map();
    new ResizeObserver(() => this._fitRows()).observe(this._history);
    this._status = root.querySelector(".status");

    this._img.addEventListener("load", () => { this._img.style.visibility = "visible"; this._hint.style.opacity = "0.0"; });
    this._img.addEventListener("error", () => { this._img.style.visibility = "hidden"; this._hint.style.opacity = "1"; });
    this._drop.addEventListener("mouseenter", () => (this._hint.style.opacity = "1"));
    this._drop.addEventListener("mouseleave", () => { if (this._img.style.visibility === "visible") this._hint.style.opacity = "0"; });
    this._img.style.visibility = "hidden";

    this._drop.addEventListener("click", () => this._file.click());
    this._file.addEventListener("change", () => {
      if (this._file.files[0]) this._upload(this._file.files[0]);
      this._file.value = "";
    });
    this._drop.addEventListener("dragover", (e) => { e.preventDefault(); this._drop.classList.add("over"); });
    this._drop.addEventListener("dragleave", () => this._drop.classList.remove("over"));
    this._drop.addEventListener("drop", (e) => {
      e.preventDefault();
      this._drop.classList.remove("over");
      const file = [...(e.dataTransfer.files || [])].find((f) => f.type.startsWith("image/"));
      if (file) return this._upload(file);
      const url = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
      if (url) this._showUrl(url.trim());
    });
    this._button.addEventListener("click", () => this._showUrl(this._url.value.trim()));
    this._url.addEventListener("keydown", (e) => { if (e.key === "Enter") this._showUrl(this._url.value.trim()); });
    this._textButton.addEventListener("click", () => this._showText());
    this._message.addEventListener("keydown", (e) => { if (e.key === "Enter") this._showText(); });
    this._color.addEventListener("change", () => {
      try { localStorage.setItem("esphome-pixoo-gallery-color", this._color.value); } catch (err) { /* private mode */ }
    });
  }

  _handlePaste(e) {
    const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
    if (file) {
      e.preventDefault();
      this._upload(file);
      return;
    }
    // Text pasted outside the link field: treat a URL as a link to show.
    const path = e.composedPath();
    const inField = path.includes(this._url) || path.includes(this._message);
    const text = e.clipboardData?.getData("text/plain")?.trim();
    if (!inField && text && /^https?:\/\//i.test(text)) {
      e.preventDefault();
      this._url.value = text;
      this._showUrl(text);
    }
  }

  _setStatus(text, error = false) {
    this._status.textContent = text;
    this._status.classList.toggle("error", error);
  }

  _busy(on) {
    this._button.disabled = on;
    this._textButton.disabled = on;
    this._drop.style.opacity = on ? "0.6" : "1";
  }

  _refreshPreview() {
    if (this._picture) this._img.src = this._picture;
    else this._img.removeAttribute("src");
  }

  // History previews need a login, which an <img> can't send, so they are fetched as blobs.
  _thumb(img, key) {
    const cached = this._thumbs.get(key);
    if (cached) {
      cached.then((url) => { if (url) img.src = url; });
      return;
    }
    const url = this._hass
      .fetchWithAuth(`/api/${DOMAIN}/${this._display.entry_id}/history/${key}`)
      .then((resp) => (resp.ok ? resp.blob() : null))
      .then((blob) => (blob ? URL.createObjectURL(blob) : null))
      .catch(() => null);
    this._thumbs.set(key, url);
    url.then((src) => { if (src) img.src = src; else this._thumbs.delete(key); });
  }

  _setHistory(items, current) {
    const keys = new Set(items.map((item) => item.key));
    for (const [key, url] of this._thumbs) {
      if (!keys.has(key)) {
        url.then((src) => src && URL.revokeObjectURL(src));
        this._thumbs.delete(key);
      }
    }
    this._items = items;
    this._current = current;
    this._historyLabel.hidden = items.length === 0;
    this._history.replaceChildren(...items.map((item) => this._tile(item, () => this._reuse(item.source))));
    this._fitRows();
    if (this._dialog) this._dialog.render(items, current);
  }

  // Show two rows on the card; the rest is in the "Show all" popup.
  _fitRows() {
    const columns = getComputedStyle(this._history).gridTemplateColumns.split(" ").filter(Boolean).length || 1;
    const shown = columns * 2;
    [...this._history.children].forEach((tile, i) => tile.classList.toggle("overflow", i >= shown));
    this._allButton.hidden = this._items.length <= shown;
    this._allButton.textContent = `Show all (${this._items.length})`;
  }

  _openAll() {
    if (!this._dialog) {
      this._dialog = document.createElement("esphome-pixoo-gallery-history");
      this._dialog.card = this;
    }
    document.body.append(this._dialog);
    this._dialog.render(this._items, this._current);
  }

  // A history tile: tap shows it again, a long press offers to remove it.
  _tile(item, onTap) {
    const button = document.createElement("button");
    if (item.key === this._current) button.classList.add("current");
    const text = PixooGalleryCard._parseText(item.source);
    if (text) {
      // A scrolling text shows as its words, not as the GIF's first (blank) frame.
      button.title = `Text: ${text.text}`;
      const label = document.createElement("span");
      label.className = "text";
      label.style.color = text.color;
      label.textContent = text.text;
      button.append(label);
    } else {
      button.title = item.source.replace("media-source://media_source/local/", "Media: ");
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      img.draggable = false;
      this._thumb(img, item.key);
      button.append(img);
    }
    let timer = null;
    let held = false;
    let start = null;
    const cancel = () => { clearTimeout(timer); timer = null; button.classList.remove("held"); };
    button.addEventListener("pointerdown", (e) => {
      held = false;
      start = [e.clientX, e.clientY];
      button.classList.add("held");
      timer = setTimeout(() => { held = true; cancel(); this._confirmForget(item, button); }, HOLD_MS);
    });
    button.addEventListener("pointermove", (e) => {
      if (timer && start && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 10) cancel();
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach((type) => button.addEventListener(type, cancel));
    button.addEventListener("contextmenu", (e) => e.preventDefault());
    button.addEventListener("click", (e) => {
      if (held) { e.preventDefault(); held = false; return; }
      onTap();
    });
    return button;
  }

  _confirmForget(item, tile) {
    const dialog = document.createElement("esphome-pixoo-gallery-confirm");
    dialog.preview = tile.cloneNode(true);
    dialog.onConfirm = () => this._forget(item);
    document.body.append(dialog);
  }

  async _forget(item) {
    this._setStatus("Removing…");
    try {
      await this._hass.callService(DOMAIN, "forget", { config_entry_id: this._display.entry_id, key: item.key });
      this._setStatus("Removed from the list");
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    }
  }

  async _reuse(source) {
    const text = PixooGalleryCard._parseText(source);
    const data = text
      ? { text: text.text, color: text.rgb }
      : source.startsWith("media-source://") ? { media: source } : { url: source };
    this._busy(true);
    try {
      await this._run(data);
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    } finally {
      this._busy(false);
    }
  }

  async _upload(file) {
    if (!this._hass) return;
    this._busy(true);
    this._setStatus("Uploading…");
    try {
      const ext = (file.type.split("/")[1] || "png").replace("jpeg", "jpg").replace(/[^a-z0-9]/gi, "");
      const name = `pixoo-${new Date().toISOString().replace(/[:.]/g, "-")}.${ext}`;
      const form = new FormData();
      form.append("file", new File([file], name, { type: file.type }));
      const resp = await this._hass.fetchWithAuth(`/api/${DOMAIN}/upload`, { method: "POST", body: form });
      if (!resp.ok) throw new Error(`upload failed (${resp.status}): ${await resp.text()}`);
      const { media_content_id } = await resp.json();
      await this._run({ media: media_content_id });
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    } finally {
      this._busy(false);
    }
  }

  async _showUrl(url) {
    if (!url || !this._hass) return;
    if (!/^https?:\/\//i.test(url)) return this._setStatus("A link starts with http:// or https://", true);
    this._busy(true);
    try {
      await this._run({ url });
      this._url.value = "";
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    } finally {
      this._busy(false);
    }
  }

  static _parseText(source) {
    const match = /^text:([0-9a-f]{6}):(.*)$/i.exec(source);
    if (!match) return null;
    let text = match[2];
    try { text = decodeURIComponent(text); } catch (err) { /* keep it as stored */ }
    const rgb = [0, 2, 4].map((i) => parseInt(match[1].slice(i, i + 2), 16));
    return { color: `#${match[1]}`, rgb, text };
  }

  async _showText() {
    const text = this._message.value.trim();
    if (!text || !this._hass) return;
    const hex = this._color.value.replace("#", "");
    const color = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
    this._busy(true);
    try {
      await this._run({ text, color });
      this._message.value = "";
    } catch (err) {
      this._setStatus(String(err.message || err), true);
    } finally {
      this._busy(false);
    }
  }

  async _run(data) {
    if (!this._display) throw new Error("No Pixoo display is set up");
    this._setStatus("Converting…");
    await this._hass.callService(DOMAIN, "show", { config_entry_id: this._display.entry_id, ...data });
    this._setStatus("Showing on the Pixoo");
  }
}

const OVERLAY_CSS = `
  :host { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; }
  .scrim { position: absolute; inset: 0; background: rgba(0,0,0,.5); }
  .panel {
    position: relative; background: var(--card-background-color, #fff); color: var(--primary-text-color);
    border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,.35); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  h2 { margin: 0; font-size: 18px; font-weight: 500; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; }
  .actions button, button.close {
    font: inherit; padding: 8px 14px; border-radius: 8px; border: 0; cursor: pointer;
    background: none; color: var(--primary-color);
  }
  .actions button.danger { background: var(--error-color, #db4437); color: #fff; }
  button.close { font-size: 22px; line-height: 1; padding: 4px 8px; color: var(--secondary-text-color); }
  .hint { font-size: 13px; color: var(--secondary-text-color); margin: 4px 0 12px; }
`;

class PixooHistoryDialog extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>${OVERLAY_CSS}${TILE_CSS}
        .panel { width: min(92vw, 560px); max-height: 85vh; display: flex; flex-direction: column; padding: 16px; box-sizing: border-box; }
        .history { overflow-y: auto; grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); padding: 2px; }
      </style>
      <div class="scrim"></div>
      <div class="panel" role="dialog" aria-modal="true">
        <div class="head"><h2></h2><button class="close" aria-label="Close">×</button></div>
        <div class="hint">Tap to show it again, hold to remove it from the list.</div>
        <div class="history"></div>
      </div>`;
    this._title = root.querySelector("h2");
    this._grid = root.querySelector(".history");
    onTap(root.querySelector(".scrim"), () => this.remove());
    onTap(root.querySelector(".close"), () => this.remove());
    this._onKey = (e) => { if (e.key === "Escape") this.remove(); };
  }

  connectedCallback() { window.addEventListener("keydown", this._onKey); }
  disconnectedCallback() { window.removeEventListener("keydown", this._onKey); }

  render(items, current) {
    if (!this.isConnected) return;
    this._title.textContent = `Earlier (${items.length})`;
    this._grid.replaceChildren(...items.map((item) => this.card._tile(item, () => {
      this.remove();
      this.card._reuse(item.source);
    })));
  }
}

class PixooConfirmDialog extends HTMLElement {
  connectedCallback() {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>${OVERLAY_CSS}${TILE_CSS}
        :host { z-index: 1001; }
        .panel { width: min(86vw, 320px); padding: 20px; box-sizing: border-box; text-align: center; }
        .history { grid-template-columns: 96px; justify-content: center; margin: 12px 0 16px; }
        .history button { pointer-events: none; }
        .actions { justify-content: center; }
      </style>
      <div class="scrim"></div>
      <div class="panel" role="alertdialog" aria-modal="true">
        <h2>Remove this from the list?</h2>
        <div class="history"></div>
        <div class="actions"><button class="cancel">Cancel</button><button class="danger">Remove</button></div>
      </div>`;
    if (this.preview) {
      this.preview.classList.remove("held", "overflow");
      root.querySelector(".history").append(this.preview);
    }
    const close = () => this.remove();
    onTap(root.querySelector(".scrim"), close);
    onTap(root.querySelector(".cancel"), close);
    onTap(root.querySelector(".danger"), () => { close(); this.onConfirm && this.onConfirm(); });
  }
}

if (!customElements.get("esphome-pixoo-gallery-card")) {
  customElements.define("esphome-pixoo-gallery-history", PixooHistoryDialog);
  customElements.define("esphome-pixoo-gallery-confirm", PixooConfirmDialog);
  customElements.define("esphome-pixoo-gallery-card", PixooGalleryCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "esphome-pixoo-gallery-card",
    name: "ESPHome Pixoo Gallery",
    description: "Paste, drop or pick an image or GIF, or type a scrolling text, to show on a Pixoo 64.",
  });
}
