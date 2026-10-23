const SLOTS = 6;

const STYLE = `
  :host {
    --tou-cell-bg: var(--secondary-background-color, #f2f3f5);
    --tou-border: var(--divider-color, rgba(0, 0, 0, 0.12));
    --tou-accent: var(--primary-color, #03a9f4);
    display: block;
  }
  ha-card { padding: 16px; container-type: inline-size; }
  .head {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px; cursor: pointer; user-select: none;
    font-size: 16px; font-weight: 500; color: var(--primary-text-color);
  }
  .head .name { flex: 1; }
  .head .state { font-size: 13px; font-weight: 400; color: var(--secondary-text-color); }
  .row {
    display: grid;
    grid-template-columns: 26px 26px minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.1fr) minmax(0, 0.95fr);
    column-gap: 8px; align-items: center;
    padding: 3px 6px; margin: 0 -6px; border-radius: 8px;
  }
  .body.am-pm .row {
    grid-template-columns: 26px 26px minmax(0, 1.3fr) minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 0.8fr);
  }
  .row + .row { margin-top: 3px; }
  .row.active { background: color-mix(in srgb, var(--tou-accent) 10%, transparent); }
  .th {
    font-size: 12px; line-height: 16px; color: var(--secondary-text-color);
    text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .th.time { grid-column: span 2; }
  .th.check { overflow: visible; text-overflow: clip; }
  .th .unit { opacity: 0.7; }
  .body.off .row:not(.thead) { opacity: 0.5; }
  input.cell {
    box-sizing: border-box; width: 100%; min-width: 0; height: 34px; margin: 0; padding: 0 4px;
    border: 1px solid var(--tou-border); border-radius: 6px;
    background: var(--tou-cell-bg); color: var(--primary-text-color);
    font: inherit; font-size: 14px; font-variant-numeric: tabular-nums; text-align: center;
    -moz-appearance: textfield; appearance: textfield;
  }
  input.cell::-webkit-inner-spin-button, input.cell::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  input.cell:focus { outline: 2px solid var(--tou-accent); outline-offset: -1px; }
  input.cell:disabled { opacity: 0.45; }
  input[type="checkbox"] {
    -webkit-appearance: none; appearance: none;
    box-sizing: border-box; width: 20px; height: 20px; margin: 0 auto; display: block;
    border: 2px solid var(--secondary-text-color); border-radius: 4px;
    background: transparent center / 14px 14px no-repeat; cursor: pointer;
  }
  input[type="checkbox"]:checked {
    border-color: var(--tou-accent); background-color: var(--tou-accent);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 12.5l5 5L20 6.5' fill='none' stroke='white' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  }
  input[type="checkbox"]:focus-visible { outline: 2px solid var(--tou-accent); outline-offset: 2px; }
  .head input[type="checkbox"] { margin: 0; }
  input[type="checkbox"]:disabled { cursor: default; opacity: 0.45; }
  input.cell.dirty {
    border-color: var(--tou-accent) !important;
    background: color-mix(in srgb, var(--tou-accent) 14%, var(--tou-cell-bg)) !important;
  }
  input[type="checkbox"].dirty { outline: 2px solid var(--tou-accent); outline-offset: 2px; border-radius: 3px; }
  .pending { opacity: 0.6; }
  input.cell.invalid {
    border-color: var(--error-color, #db4437) !important;
    background: color-mix(in srgb, var(--error-color, #db4437) 14%, var(--tou-cell-bg)) !important;
  }
  .foot { display: flex; align-items: center; gap: 8px; margin-top: 14px; min-height: 36px; }
  .status { flex: 1; min-width: 0; font-size: 13px; color: var(--secondary-text-color); }
  .status.error { color: var(--error-color, #db4437); }
  button {
    height: 36px; padding: 0 16px; border-radius: 18px; cursor: pointer;
    font: inherit; font-size: 14px; font-weight: 500;
    border: 1px solid var(--tou-border); background: transparent; color: var(--primary-text-color);
  }
  button.save { border-color: var(--tou-accent); background: var(--tou-accent); color: var(--text-primary-color, #fff); }
  button:disabled { cursor: default; opacity: 0.4; }
  .note { font-size: 13px; color: var(--secondary-text-color); }
  @container (max-width: 380px) {
    ha-card { padding: 12px; }
    .row { column-gap: 5px; grid-template-columns: 26px 26px minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.1fr) minmax(0, 0.95fr); }
    .th { font-size: 11px; }
    .body.am-pm input.cell[data-key^="time"] { font-size: 12px; padding: 0 1px; }
    input.cell { font-size: 13px; height: 32px; padding: 0 2px; }
    button { padding: 0 12px; }
  }
`;

const toMinutes = (text) => {
  const m = String(text ?? "").trim().match(/^(\d{1,2}):?(\d{2})(?::\d{2})?$/);
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  return Number(m[1]) * 60 + Number(m[2]);
};

const formatTime = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

const displayTime = (minutes, amPm) => {
  if (!amPm) return formatTime(minutes);
  const hour = Math.floor(minutes / 60);
  return `${hour % 12 || 12}:${String(minutes % 60).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
};

const parseInput = (text) => {
  const m = String(text ?? "").trim().match(/^(\d{1,2})(?::?(\d{2}))?\s*([ap])\.?\s*m?\.?$/i);
  if (!m) return toMinutes(text);
  const hour = Number(m[1]);
  const minute = Number(m[2] ?? 0);
  if (hour < 1 || hour > 12 || minute > 59) return null;
  return ((hour % 12) + (m[3].toLowerCase() === "p" ? 12 : 0)) * 60 + minute;
};

// Same rule as the Home Assistant frontend, so the card matches the user's
// profile setting rather than the browser's time input locale.
const usesAmPm = (locale) => {
  const format = locale?.time_format;
  if (!format || format === "language" || format === "system") {
    const lang = format === "system" ? undefined : locale?.language;
    try {
      return new Date("January 1, 2023 22:00:00").toLocaleString(lang).includes("10");
    } catch (e) {
      return false;
    }
  }
  return format === "am_pm";
};

const sameValue = (a, b) => (typeof a === "number" && typeof b === "number" ? Math.abs(a - b) < 1e-9 : a === b);

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v);
  }
  el.append(...children);
  return el;
};

const checkbox = (key, label) => h("input", { type: "checkbox", "data-key": key, "aria-label": label });

const cell = (type, key, label) =>
  h("input", {
    class: "cell", type, "data-key": key, "aria-label": label,
    inputmode: "numeric", autocomplete: "off",
    ...(type === "time" ? { type: "text", maxlength: "8" } : {}),
  });

const FIELDS = ["time", "power", "batt", "grid_charge", "gen"];

/**
 * Builds the card for one integration. ``adapter``:
 *   domain        integration domain; its devices, TOU switch and set_tou_schedule action
 *   type, name, description, documentationURL   card picker entry
 *   readSchedule  turns the switch's ``schedule`` attribute into six slots of
 *                 {time: "HH:MM", power, batt, grid_charge, gen}
 *   pendingMs     how long a saved value is shown before the integration reports it
 *   minuteStep    optional; slot times must fall on this many minutes
 */
export function defineTouCard(adapter) {
  if (customElements.get(adapter.type)) return;

  const scheduleOf = (hass, entityId) => {
    const raw = hass.states[entityId]?.attributes?.schedule;
    return Array.isArray(raw) ? adapter.readSchedule(raw) : null;
  };

  const touSwitches = (hass, device) =>
    Object.values(hass.entities || {})
      .filter(
        (e) =>
          e.platform === adapter.domain &&
          e.entity_id.startsWith("switch.") &&
          (!device || e.device_id === device) &&
          Array.isArray(hass.states[e.entity_id]?.attributes?.schedule),
      );

  class TouCard extends HTMLElement {
    constructor() {
      super();
      this._draft = new Map();
      this._pending = new Map();
      this._saving = false;
      this._status = "";
      this._error = false;
      this._preview = false;
    }

    static getStubConfig(hass) {
      const [entry] = touSwitches(hass);
      return entry ? { device: entry.device_id } : {};
    }

    static getConfigForm() {
      return {
        schema: [
          { name: "device", selector: { device: { integration: adapter.domain } } },
          { name: "title", selector: { text: {} } },
        ],
        computeLabel: (field) => ({ device: "Inverter", title: "Title" })[field.name],
        computeHelper: (field) =>
          field.name === "device" ? "Leave empty to use the first inverter found." : undefined,
      };
    }

    setConfig(config) {
      if (!config || typeof config !== "object") throw new Error("Invalid configuration");
      for (const key of ["device", "title"]) {
        if (config[key] !== undefined && typeof config[key] !== "string") {
          throw new Error(`"${key}" has to be text`);
        }
      }
      this._config = { ...config };
      this._entityId = undefined;
      this._draft.clear();
      this._pending.clear();
      if (this._hass) this.hass = this._hass;
    }

    // Set by the card editor; the preview there must not write to the inverter.
    set preview(value) {
      this._preview = !!value;
      this._sync();
    }

    getCardSize() {
      return 7;
    }

    getGridOptions() {
      return { columns: 12, min_columns: 6 };
    }

    set hass(hass) {
      this._hass = hass;
      const [entry] = touSwitches(hass, this._config?.device);
      if ((entry?.entity_id ?? null) !== this._entityId) {
        this._entityId = entry?.entity_id ?? null;
        this._deviceId = entry?.device_id ?? null;
        this._build();
      }
      this._sync();
    }

    _current(key) {
      if (key === "tou") {
        const state = this._hass.states[this._entityId]?.state;
        return state === "on" ? true : state === "off" ? false : undefined;
      }
      const slots = scheduleOf(this._hass, this._entityId);
      const [field, index] = key.split(":");
      return slots?.[Number(index)]?.[field] ?? undefined;
    }

    _shown(key) {
      if (this._draft.has(key)) return this._draft.get(key);
      if (this._pending.has(key)) return this._pending.get(key).value;
      return this._current(key);
    }

    _build() {
      const root = this.shadowRoot || this.attachShadow({ mode: "open" });
      const card = h("ha-card");
      root.replaceChildren(h("style", { text: STYLE }), card);
      this._els = new Map();
      this._rows = [];
      this._ready = false;
      this._draft.clear();
      this._pending.clear();

      if (!this._entityId) {
        card.append(h("div", { class: "note", text: `No ${adapter.name} schedule found.` }));
        return;
      }

      this._stateEl = h("span", { class: "state" });
      card.append(
        h("label", { class: "head" },
          checkbox("tou", "Time Of Use"),
          h("span", { class: "name", text: this._config.title || "Time Of Use" }),
          this._stateEl),
      );

      const unit = (text) => h("span", { class: "unit", text });
      this._body = h("div", { class: "body" },
        h("div", { class: "row thead" },
          h("div", { class: "th check", title: "Grid charge", text: "Grid" }),
          h("div", { class: "th check", title: "Generator charge", text: "Gen" }),
          h("div", { class: "th time", text: "Time" }),
          h("div", { class: "th" }, "Power ", unit("W")),
          h("div", { class: "th" }, "Batt ", unit("%"))));
      for (let i = 0; i < SLOTS; i++) {
        const n = i + 1;
        const row = h("div", { class: "row" },
          checkbox(`grid_charge:${i}`, `Slot ${n} grid charge`),
          checkbox(`gen:${i}`, `Slot ${n} generator charge`),
          cell("time", `time:${i}`, `Slot ${n} start`),
          cell("time", `time:${n % SLOTS}`, `Slot ${n} end`),
          cell("number", `power:${i}`, `Slot ${n} power`),
          cell("number", `batt:${i}`, `Slot ${n} battery SOC`));
        this._body.append(row);
        this._rows.push(row);
      }
      card.append(this._body);

      this._statusEl = h("div", { class: "status", role: "status" });
      this._discardBtn = h("button", { class: "discard", type: "button", text: "Discard" });
      this._saveBtn = h("button", { class: "save", type: "button", text: "Save" });
      this._discardBtn.addEventListener("click", () => this._discard());
      this._saveBtn.addEventListener("click", () => this._save());
      card.append(h("div", { class: "foot" }, this._statusEl, this._discardBtn, this._saveBtn));

      for (const el of card.querySelectorAll("[data-key]")) {
        const key = el.dataset.key;
        if (!this._els.has(key)) this._els.set(key, []);
        this._els.get(key).push(el);
        const bool = el.type === "checkbox";
        el.addEventListener(bool ? "change" : "input", () => this._edit(key, el));
        if (key.startsWith("time")) el.addEventListener("blur", () => setTimeout(() => this._sync()));
      }
      this._ready = true;
    }

    _edit(key, el) {
      let value;
      if (el.type === "checkbox") value = el.checked;
      else if (key.startsWith("time")) {
        const minutes = parseInput(el.value);
        value = minutes === null ? el.value.trim() : formatTime(minutes);
      } else value = el.value === "" ? undefined : Number(el.value);
      const current = this._current(key);
      if (value !== undefined && current !== undefined && sameValue(value, current)) this._draft.delete(key);
      else this._draft.set(key, value);
      if (!this._saving) {
        this._status = "";
        this._error = false;
      }
      this._sync();
    }

    _discard() {
      this._draft.clear();
      this._status = "";
      this._error = false;
      this._sync();
    }

    _invalid() {
      const bad = new Map();
      const order = "Slot times must go in order.";
      const times = [];
      for (let i = 0; i < SLOTS; i++) times.push(toMinutes(this._shown(`time:${i}`)));
      for (let i = 0; i < SLOTS; i++) {
        if (times[i] === null) {
          if (this._draft.has(`time:${i}`)) {
            bad.set(`time:${i}`, `Enter times like ${displayTime(330, usesAmPm(this._hass.locale))}.`);
          }
        } else if (adapter.minuteStep && times[i] % adapter.minuteStep) {
          bad.set(`time:${i}`, `Times have to be in ${adapter.minuteStep}-minute steps.`);
        } else if (i > 0 && times[i - 1] !== null && times[i] <= times[i - 1]) {
          bad.set(`time:${i}`, order);
          bad.set(`time:${i - 1}`, order);
        }
      }
      for (const [key, v] of this._draft) {
        const [field] = key.split(":");
        if (field !== "power" && field !== "batt") continue;
        const name = field === "batt" ? "Battery" : "Power";
        if (v === undefined || !Number.isFinite(v)) bad.set(key, `${name} needs a value.`);
        else if (v < 0) bad.set(key, `${name} can't be negative.`);
        else if (field === "batt" && v > 100) bad.set(key, "Battery must be at most 100.");
      }
      return bad;
    }

    _activeSlot() {
      const times = [];
      for (let i = 0; i < SLOTS; i++) {
        const t = toMinutes(this._current(`time:${i}`));
        if (t === null) return -1;
        times.push(t);
      }
      let now;
      try {
        now = toMinutes(
          new Intl.DateTimeFormat("en-GB", {
            hour: "2-digit", minute: "2-digit", hourCycle: "h23",
            timeZone: this._hass.config?.time_zone,
          }).format(new Date()),
        );
      } catch (e) {
        const d = new Date();
        now = d.getHours() * 60 + d.getMinutes();
      }
      let active = -1;
      let best = -1;
      times.forEach((t, i) => {
        if (t <= now && t > best) {
          best = t;
          active = i;
        }
      });
      if (active === -1) active = times.indexOf(Math.max(...times));
      return active;
    }

    _sync() {
      if (!this._hass || !this._ready) return;
      const now = Date.now();
      for (const [key, p] of this._pending) {
        const current = this._current(key);
        if (now > p.until || (current !== undefined && sameValue(current, p.value))) this._pending.delete(key);
      }

      const state = this._hass.states[this._entityId];
      const unavailable = !state || state.state === "unavailable";
      const known = !!scheduleOf(this._hass, this._entityId);
      const invalid = this._invalid();
      const focused = this.shadowRoot.activeElement;
      const amPm = usesAmPm(this._hass.locale);
      this._body.classList.toggle("am-pm", amPm);
      const locked = unavailable || this._saving || this._preview;

      for (const [key, els] of this._els) {
        const value = this._shown(key);
        for (const el of els) {
          if (el.type === "checkbox") el.checked = !!value;
          else if (key.startsWith("time")) {
            const minutes = toMinutes(value);
            if (el !== focused) el.value = minutes === null ? value ?? "" : displayTime(minutes, amPm);
            el.inputMode = amPm ? "text" : "numeric";
            el.placeholder = amPm ? "12:00 AM" : "00:00";
          } else if (el !== focused) el.value = value === undefined ? "" : String(value);
          if (key.startsWith("batt")) el.max = 100;
          el.min = 0;
          el.disabled = locked || (key !== "tou" && !known);
          el.classList.toggle("dirty", this._draft.has(key));
          el.classList.toggle("pending", this._pending.has(key));
          el.classList.toggle("invalid", invalid.has(key));
          el.title = invalid.get(key) || (unavailable ? "Unavailable" : "");
        }
      }

      const touOn = this._shown("tou");
      this._body.classList.toggle("off", touOn === false);
      this._stateEl.textContent = unavailable ? "Unavailable" : touOn === false ? "Off" : "";

      const active = touOn === false ? -1 : this._activeSlot();
      this._rows.forEach((row, i) => row.classList.toggle("active", i === active));

      const changes = this._draft.size;
      let status = this._status;
      let error = this._error;
      if (!status && invalid.size) {
        status = invalid.values().next().value;
        error = true;
      } else if (!status && changes) {
        status = changes === 1 ? "1 change" : `${changes} changes`;
      }
      this._statusEl.textContent = status;
      this._statusEl.classList.toggle("error", error);
      this._saveBtn.disabled = locked || !changes || invalid.size > 0;
      this._discardBtn.disabled = this._saving || !changes;
    }

    // Only edited fields are sent; the integration keeps the rest as the inverter
    // holds them at write time, so a change made on the inverter since the last
    // update is not undone.
    _slots(keys) {
      const slots = Array.from({ length: SLOTS }, () => ({}));
      for (const key of keys) {
        const [field, index] = key.split(":");
        slots[Number(index)][field] = this._draft.get(key);
      }
      return slots;
    }

    _steps() {
      const slotKeys = [...this._draft.keys()].filter((key) => key !== "tou");
      const steps = [];
      if (slotKeys.length) {
        const data = { slots: this._slots(slotKeys) };
        if (this._deviceId) data.device_id = this._deviceId;
        steps.push({
          keys: slotKeys,
          run: () => this._hass.callService(adapter.domain, "set_tou_schedule", data),
        });
      }
      if (this._draft.has("tou")) {
        const on = this._draft.get("tou");
        steps.push({
          keys: ["tou"],
          run: () =>
            this._hass.callService("switch", on ? "turn_on" : "turn_off", {}, { entity_id: this._entityId }),
        });
      }
      return steps;
    }

    async _save() {
      if (this._saving || this._preview || !this._draft.size || this._invalid().size) return;
      const steps = this._steps();
      this._saving = true;
      this._error = false;
      let done = 0;
      try {
        for (const step of steps) {
          this._status = steps.length > 1 ? `Saving ${done + 1} of ${steps.length}` : "Saving";
          this._sync();
          const values = step.keys.map((key) => this._draft.get(key));
          await step.run();
          step.keys.forEach((key, i) => {
            this._draft.delete(key);
            this._pending.set(key, { value: values[i], until: Date.now() + adapter.pendingMs });
          });
          done++;
        }
        this._status = "Saved";
      } catch (err) {
        this._status = `${err?.message || "Write failed"}${done ? ` (${done} of ${steps.length} saved)` : ""}`;
        this._error = true;
      } finally {
        this._saving = false;
        this._sync();
      }
      if (!this._error) {
        setTimeout(() => {
          if (this._status === "Saved") {
            this._status = "";
            this._sync();
          }
        }, 4000);
      }
    }
  }

  customElements.define(adapter.type, TouCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: adapter.type,
    name: adapter.name,
    description: adapter.description,
    documentationURL: adapter.documentationURL,
    preview: true,
  });
}
