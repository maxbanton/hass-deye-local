// Battery card: a battery that fills with the state of charge, coloured by level,
// with whether it is charging or discharging, at what power and for how long.
// Narrow, it is a compact battery; wide, the runtime becomes the headline.

const DOMAIN = "deye_local";
const TYPE = "deye-local-battery-card";
// Battery power is negative while the battery charges; below this it counts as idle.
const IDLE_WATTS = 20;
const RED_BELOW = 20;
const AMBER_BELOW = 50;
// Below this the inverter is off grid: it reports no frequency without a grid.
const GRID_HZ = 40;
// From this card width on, the wide layout is used.
const WIDE_PX = 300;

const BOLT = "M11,15H6L13,1V9H18L11,23V15Z";

const STYLE = `
  :host { display: block; }
  ha-card {
    height: 100%; box-sizing: border-box; cursor: pointer;
    display: flex; flex-direction: column; justify-content: center;
    padding: 16px 12px 12px; gap: 6px;
  }
  ha-card:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  ha-card.missing { cursor: default; }
  ha-card.missing > :not(.warning), ha-card:not(.missing) > .warning { display: none; }
  [hidden] { display: none !important; }

  .battery { align-self: center; width: 100%; max-width: 158px; display: flex; flex-direction: column; }
  /* The frame holds the body and the tip. Its limit marks and their ticks share the
     fill's scale: the fill starts after the 3px border and 3px padding on each side. */
  .frame { position: relative; margin-right: 8px; }
  .body {
    position: relative; height: 56px; box-sizing: border-box; overflow: hidden;
    border: 3px solid var(--secondary-text-color); border-radius: 10px; padding: 3px;
  }
  .nub {
    position: absolute; left: 100%; top: 50%; transform: translateY(-50%);
    width: 6px; height: 40%; margin-left: 2px;
    border-radius: 0 3px 3px 0; background: var(--secondary-text-color);
  }
  .fill {
    position: relative; overflow: hidden; height: 100%; border-radius: 5px;
    background: var(--battery-color);
    transition: width 0.8s ease, background-color 0.8s ease;
  }
  .charging .fill::after, .discharging .fill::after {
    content: ""; position: absolute; inset: 0;
    background-image: linear-gradient(45deg,
      rgba(255, 255, 255, 0.16) 25%, transparent 25%, transparent 50%,
      rgba(255, 255, 255, 0.16) 50%, rgba(255, 255, 255, 0.16) 75%, transparent 75%);
    background-size: 16px 16px;
    animation: stripes 1.6s linear infinite;
  }
  .discharging .fill::after { animation-direction: reverse; }
  @keyframes stripes { from { background-position: 0 0; } to { background-position: 16px 0; } }
  .value {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: var(--primary-text-color); font-size: 24px; font-weight: var(--ha-font-weight-medium, 500);
    font-variant-numeric: tabular-nums;
  }
  /* A dark copy of the number clipped to the filled part: the theme's text colour
     is light in dark themes and unreadable on amber or green. */
  .value.on-fill {
    color: rgba(0, 0, 0, 0.87);
    clip-path: inset(0 calc(100% - 3px - (100% - 6px) * var(--level)) 0 0);
    transition: clip-path 0.8s ease;
  }

  /* A limit: a solid mark through the battery's edge, a dashed tick and a label. */
  .notch {
    position: absolute; width: 2px; height: 8px; margin-left: -1px; border-radius: 1px;
    left: calc(6px + (100% - 12px) * var(--at)); background: var(--primary-text-color);
  }
  .notch.down { bottom: -2px; }
  .notch.up { top: -2px; }
  .ticks { position: relative; margin-right: 8px; }
  .ticks.down { height: 30px; }
  .ticks.up { height: 30px; }
  .ticks.up:not(.used) { display: none; }
  .tick {
    position: absolute; display: flex; flex-direction: column; align-items: center;
    left: calc(6px + (100% - 12px) * var(--at)); transform: translateX(-50%);
  }
  .ticks.down .tick { top: 2px; }
  .ticks.up .tick { bottom: 2px; flex-direction: column-reverse; }
  .tick i { display: block; height: 6px; border-left: 1.5px dashed var(--primary-text-color); opacity: 0.7; }
  .tick b {
    font-weight: 400; font-size: 10px; line-height: 11px; text-align: center; white-space: nowrap;
    color: var(--secondary-text-color);
  }
  .tick b span { display: block; }
  .tick b em { display: block; font-style: normal; font-weight: var(--ha-font-weight-medium, 500); color: var(--primary-text-color); }
  .bare .tick b span { display: none; }

  .name { align-self: center; color: var(--primary-text-color); font-size: var(--ha-font-size-m, 14px); line-height: 20px; }
  .status {
    align-self: center; display: flex; align-items: center; gap: 2px; white-space: nowrap;
    color: var(--secondary-text-color); font-size: var(--ha-font-size-s, 12px); line-height: 16px;
  }
  .status svg { width: 14px; height: 14px; fill: var(--battery-color); flex: none; }
  .warning { padding: 16px; color: var(--error-color); }

  /* Wide: the runtime is the headline and the battery a slimmer bar under it. */
  .head { display: none; }
  ha-card.wide { padding: 16px 16px 10px; gap: 0; }
  ha-card.wide .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin-bottom: 14px; }
  ha-card.wide .battery { max-width: none; }
  ha-card.wide .body { height: 40px; }
  ha-card.wide .value, ha-card.wide .name, ha-card.wide .compact { display: none; }
  ha-card.wide .tick b { font-size: 12px; line-height: 15px; }
  ha-card.wide .ticks.down, ha-card.wide .ticks.up { height: 40px; }
  ha-card.wide .tick i { height: 8px; }
  .lead { min-width: 0; }
  .label { color: var(--secondary-text-color); font-size: var(--ha-font-size-m, 14px); line-height: 20px; margin-bottom: 2px; }
  .big {
    color: var(--primary-text-color); font-size: 40px; line-height: 1; letter-spacing: -0.5px;
    font-weight: var(--ha-font-weight-medium, 500); font-variant-numeric: tabular-nums; white-space: nowrap;
  }
  .big small {
    font-size: 16px; font-weight: var(--ha-font-weight-normal, 400); letter-spacing: 0;
    color: var(--secondary-text-color); margin: 0 6px 0 2px;
  }
  .big small:last-child { margin-right: 0; }
  .side { display: flex; flex-direction: column; align-items: flex-end; text-align: right; }
  .soc { color: var(--primary-text-color); font-size: 22px; line-height: 28px; font-weight: var(--ha-font-weight-medium, 500); font-variant-numeric: tabular-nums; }
  .side .status { align-self: flex-end; }

  @media (prefers-reduced-motion: reduce) {
    .charging .fill::after, .discharging .fill::after { animation: none; }
    .fill, .value.on-fill { transition: none; }
  }
`;

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function bolt() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", BOLT);
  svg.append(path);
  return svg;
}

// The inverter's own entities are found by their keys, so the card needs no entity picking.
function entityOf(hass, device, key) {
  return Object.values(hass.entities || {}).find(
    (e) => e.platform === DOMAIN && e.translation_key === key && (!device || e.device_id === device),
  );
}

function color(level, redBelow, amberBelow) {
  if (level < redBelow) return "var(--error-color, #db4437)";
  if (level < amberBelow) return "var(--warning-color, #ffa600)";
  return "var(--success-color, #43a047)";
}

function numberOrNull(value) {
  const n = Number(value);
  return value !== undefined && value !== null && value !== "" && Number.isFinite(n) ? n : null;
}

// Whole hours and minutes in 5 minute steps; past 10 hours the minutes are noise.
function durationParts(hours) {
  const minutes = Math.max(5, Math.round((hours * 60) / 5) * 5);
  if (minutes < 60) return [[minutes, "min"]];
  if (hours >= 10) return [[Math.round(hours), "h"]];
  const rest = minutes % 60;
  return rest ? [[Math.floor(minutes / 60), "h"], [rest, "min"]] : [[minutes / 60, "h"]];
}

function clockMinutes(value) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

// The slot in force now: the last one that started today, or else the last of the
// day before, since the table wraps around midnight.
function activeSlot(schedule, now) {
  const slots = (Array.isArray(schedule) ? schedule : [])
    .map((slot) => ({ slot, start: clockMinutes(slot?.time) }))
    .filter((s) => s.start !== null);
  if (!slots.length) return null;
  const started = slots.filter((s) => s.start <= now);
  const pick = (list) => list.reduce((a, b) => (b.start > a.start ? b : a));
  return pick(started.length ? started : slots).slot;
}

function overlap(a, b, gap = 4) {
  const x = a.getBoundingClientRect();
  const y = b.getBoundingClientRect();
  return x.right + gap > y.left && y.right + gap > x.left;
}

class BatteryCard extends HTMLElement {
  static getStubConfig(hass) {
    const soc = entityOf(hass, undefined, "battery_soc");
    return soc?.device_id ? { device: soc.device_id } : {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "device", selector: { device: { integration: DOMAIN } } },
        { name: "name", selector: { text: {} } },
        { name: "capacity", selector: { number: { min: 1, max: 10000, step: 1, mode: "box", unit_of_measurement: "Ah" } } },
        { name: "shutdown_soc", selector: { number: { min: 0, max: 100, step: 1, mode: "box", unit_of_measurement: "%" } } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "red_below", selector: { number: { min: 0, max: 100, step: 1, mode: "box", unit_of_measurement: "%" } } },
            { name: "amber_below", selector: { number: { min: 0, max: 100, step: 1, mode: "box", unit_of_measurement: "%" } } },
          ],
        },
      ],
      computeLabel: (field) =>
        ({
          device: "Inverter",
          name: "Name",
          capacity: "Battery capacity",
          shutdown_soc: "Shutdown SOC",
          red_below: `Red below (default ${RED_BELOW} %)`,
          amber_below: `Amber below (default ${AMBER_BELOW} %)`,
        })[field.name],
      computeHelper: (field) =>
        ({
          device: "Leave empty to use the first inverter found.",
          capacity: "For the runtime estimate. Leave empty to add up the battery modules' Capacity sensors.",
          shutdown_soc: "Used only when the inverter does not report its own.",
        })[field.name],
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    for (const key of ["device", "name"]) {
      if (config[key] !== undefined && typeof config[key] !== "string") {
        throw new Error(`"${key}" has to be text`);
      }
    }
    if (config.capacity !== undefined && !(numberOrNull(config.capacity) > 0)) {
      throw new Error('"capacity" has to be a positive number of Ah');
    }
    for (const key of ["shutdown_soc", "red_below", "amber_below"]) {
      const value = numberOrNull(config[key]);
      if (config[key] !== undefined && (value === null || value < 0 || value > 100)) {
        throw new Error(`"${key}" has to be between 0 and 100`);
      }
    }
    if ((numberOrNull(config.red_below) ?? RED_BELOW) > (numberOrNull(config.amber_below) ?? AMBER_BELOW)) {
      throw new Error('"red_below" can not be above "amber_below"');
    }
    this._config = config;
    this._key = null;
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    const sources = this._sources();
    const ids = [sources.soc, sources.power, sources.voltage, sources.shutdown, sources.frequency, sources.tou, ...sources.modules];
    const key = JSON.stringify([
      ids,
      ids.map((id) => hass.states[id]?.state),
      hass.states[sources.tou]?.attributes?.schedule,
      this._now(),
      hass.locale?.language,
      hass.locale?.number_format,
    ]);
    if (key === this._key) return;
    this._key = key;
    this._update();
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { columns: 6, rows: 3, min_columns: 3, min_rows: 2 };
  }

  connectedCallback() {
    if (!this._resize && "ResizeObserver" in window) {
      this._resize = new ResizeObserver(() => this._layout());
      this._resize.observe(this);
    }
    requestAnimationFrame(() => this._layout());
  }

  disconnectedCallback() {
    this._resize?.disconnect();
    this._resize = null;
  }

  _sources() {
    const hass = this._hass;
    const soc = hass && this._config ? entityOf(hass, this._config.device, "battery_soc") : undefined;
    if (!soc) return { modules: [] };
    const device = soc.device_id;
    const modules = Object.values(hass.entities || {})
      .filter((e) => e.platform === DOMAIN && e.translation_key === "capacity" && hass.devices?.[e.device_id]?.via_device_id === device)
      .map((e) => e.entity_id);
    const id = (key) => entityOf(hass, device, key)?.entity_id;
    return {
      soc: soc.entity_id,
      power: id("battery_power"),
      voltage: id("battery_voltage"),
      shutdown: id("shutdown_soc"),
      frequency: id("grid_frequency"),
      tou: id("time_of_use"),
      modules,
    };
  }

  _value(entityId) {
    return numberOrNull(this._hass.states[entityId]?.state);
  }

  // Minutes since midnight in Home Assistant's time zone, which the inverter's clock follows.
  _now() {
    const zone = this._hass?.config?.time_zone;
    try {
      const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
      return clockMinutes(parts);
    } catch {
      const now = new Date();
      return now.getHours() * 60 + now.getMinutes();
    }
  }

  _locale() {
    const format = this._hass.locale?.number_format;
    if (!format || format === "language") return this._hass.locale?.language;
    if (format === "system") return undefined;
    return { comma_decimal: "en-US", decimal_comma: "de-DE", space_comma: "fr-FR" }[format] || "en-US";
  }

  _watts(value) {
    const abs = Math.abs(value);
    if (abs < 1000) return `${Math.round(abs)} W`;
    return `${new Intl.NumberFormat(this._locale(), { maximumFractionDigits: 1 }).format(abs / 1000)} kW`;
  }

  _capacity(sources) {
    const configured = numberOrNull(this._config.capacity);
    if (configured) return configured;
    const modules = sources.modules.map((id) => this._value(id));
    return modules.length && modules.every((v) => v > 0) ? modules.reduce((a, b) => a + b, 0) : null;
  }

  // The active time of use slot and the shutdown SOC, from the inverter or the card's option.
  _limits(sources) {
    const tou = this._hass.states[sources.tou];
    const slot = tou?.state === "on" ? activeSlot(tou.attributes?.schedule, this._now()) : null;
    return {
      slot,
      slotSoc: numberOrNull(slot?.batt),
      shutdown: this._value(sources.shutdown) ?? numberOrNull(this._config.shutdown_soc),
    };
  }

  // The time of use slot's SOC is the grid charge target, and while the grid is up
  // the battery does not discharge below it. Off grid it runs down to the shutdown SOC.
  _target(sources, soc, mode) {
    const { slot, slotSoc, shutdown: known } = this._limits(sources);
    if (mode === "charging") {
      return slot?.grid_charge && slotSoc !== null && slotSoc > soc ? slotSoc : 100;
    }
    const shutdown = known ?? 0;
    const onGrid = (this._value(sources.frequency) ?? 0) >= GRID_HZ;
    return onGrid && slotSoc !== null && slotSoc > shutdown ? slotSoc : shutdown;
  }

  // Rough, like the inverter app's: linear in SOC, at the present voltage and power.
  _runtime(sources, soc, power, mode) {
    if (mode !== "charging" && mode !== "discharging") return null;
    const capacity = this._capacity(sources);
    const voltage = this._value(sources.voltage);
    if (!capacity || !voltage) return null;
    const target = this._target(sources, soc, mode);
    if ((mode === "charging" && soc >= target) || (mode === "discharging" && soc <= target)) return null;
    const hours = ((Math.abs(target - soc) / 100) * capacity * voltage) / Math.abs(power);
    const parts = durationParts(hours);
    // "Lasts" only when the battery runs to its end; on grid the inverter switches over at the slot SOC.
    let label;
    if (mode === "discharging" && target <= (this._limits(sources).shutdown ?? 0)) label = "Lasts";
    else label = target >= 100 ? "Full in" : `${Math.round(target)}% in`;
    return { label, parts, text: `${label} ~${parts.map(([n, u]) => `${n} ${u}`).join(" ")}` };
  }

  _moreInfo() {
    if (!this._soc) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: this._soc }, bubbles: true, composed: true }));
  }

  _statusLine() {
    const icon = bolt();
    const text = document.createTextNode("");
    return { node: el("div", { class: "status" }, [icon, text]), icon, text };
  }

  _limit(title) {
    const name = el("span", { text: title });
    const value = el("em");
    return {
      notch: el("div", { class: "notch down" }),
      tick: el("div", { class: "tick", title }, [el("i"), el("b", {}, [name, value])]),
      value,
    };
  }

  // Built once and updated in place: replacing the elements on every update would
  // restart the stripes, skip the fill animation and drop keyboard focus.
  _build() {
    this.attachShadow({ mode: "open" });
    const r = {};
    r.label = el("div", { class: "label" });
    r.big = el("div", { class: "big" });
    r.soc = el("div", { class: "soc" });
    r.sideStatus = this._statusLine();
    r.head = el("div", { class: "head" }, [
      el("div", { class: "lead" }, [r.label, r.big]),
      el("div", { class: "side" }, [r.soc, r.sideStatus.node]),
    ]);

    r.fill = el("div", { class: "fill" });
    r.value = el("div", { class: "value" });
    r.onFill = el("div", { class: "value on-fill" });
    r.target = this._limit("Target");
    r.shutdown = this._limit("Shutdown");
    r.up = el("div", { class: "ticks up" });
    r.down = el("div", { class: "ticks down" }, [r.shutdown.tick, r.target.tick]);
    r.battery = el("div", { class: "battery" }, [
      r.up,
      el("div", { class: "frame", "aria-hidden": "true" }, [
        el("div", { class: "body" }, [r.fill, r.value, r.onFill]),
        el("div", { class: "nub" }),
        r.shutdown.notch,
        r.target.notch,
      ]),
      r.down,
    ]);

    r.name = el("div", { class: "name" });
    r.status = this._statusLine();
    r.status.node.classList.add("compact");
    r.runtime = el("div", { class: "status compact" });
    r.warning = el("div", { class: "warning", text: "No Deye Local battery SOC sensor found" });
    r.card = el("ha-card", { role: "button", tabindex: "0" }, [r.head, r.battery, r.name, r.status.node, r.runtime, r.warning]);
    r.card.addEventListener("click", () => {
      // A tap should not leave a focus ring behind once the dialog closes.
      r.card.blur();
      this._moreInfo();
    });
    r.card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        this._moreInfo();
      }
    });
    this.shadowRoot.append(el("style", { text: STYLE }), r.card);
    this._r = r;
  }

  _update() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) this._build();
    const r = this._r;
    const sources = this._sources();
    this._soc = sources.soc;
    r.card.classList.toggle("missing", !sources.soc);
    if (!sources.soc) {
      r.card.removeAttribute("role");
      r.card.removeAttribute("tabindex");
      return;
    }
    r.card.setAttribute("role", "button");
    r.card.setAttribute("tabindex", "0");

    const soc = this._value(sources.soc);
    const known = soc !== null;
    const level = known ? Math.min(Math.max(soc, 0), 100) : 0;
    const shown = known ? `${Math.round(level)}%` : "?";
    const power = this._value(sources.power);
    let mode = null;
    if (known && power !== null) {
      mode = Math.abs(power) < IDLE_WATTS ? "idle" : power < 0 ? "charging" : "discharging";
    }
    const statusText = known
      ? { idle: "Idle", charging: `Charging ${this._watts(power ?? 0)}`, discharging: `Discharging ${this._watts(power ?? 0)}` }[mode]
      : "Unavailable";
    const runtime = known ? this._runtime(sources, level, power, mode) : null;
    const name = this._config.name || "Battery";

    r.battery.classList.toggle("charging", mode === "charging");
    r.battery.classList.toggle("discharging", mode === "discharging");
    r.fill.style.width = `${level}%`;
    r.value.textContent = shown;
    r.onFill.textContent = shown;
    r.name.textContent = name;
    for (const line of [r.status, r.sideStatus]) {
      line.icon.toggleAttribute("hidden", mode !== "charging");
      line.text.data = statusText || "";
      line.node.toggleAttribute("hidden", !statusText);
    }
    r.runtime.textContent = runtime?.text || "";
    r.runtime.hidden = !runtime;

    // Wide headline: the runtime when there is one, otherwise the charge itself.
    r.label.textContent = runtime ? runtime.label : name;
    r.big.replaceChildren(
      ...(runtime
        ? runtime.parts.flatMap(([n, u]) => [document.createTextNode(String(n)), el("small", { text: u })])
        : [document.createTextNode(shown)]),
    );
    r.soc.textContent = shown;
    r.soc.hidden = !runtime;

    const redBelow = numberOrNull(this._config.red_below) ?? RED_BELOW;
    const amberBelow = numberOrNull(this._config.amber_below) ?? AMBER_BELOW;
    r.card.style.setProperty("--battery-color", color(level, redBelow, amberBelow));
    r.card.style.setProperty("--level", String(level / 100));

    // A limit at either end of the battery says nothing the battery itself does not.
    const { slotSoc, shutdown } = this._limits(sources);
    const showShutdown = shutdown !== null && shutdown > 0 && shutdown < 100;
    const showTarget = slotSoc !== null && slotSoc > 0 && slotSoc < 100 && slotSoc !== shutdown;
    for (const [limit, value, show] of [[r.target, slotSoc, showTarget], [r.shutdown, shutdown, showShutdown]]) {
      limit.notch.hidden = limit.tick.hidden = !show;
      if (!show) continue;
      const at = String(value / 100);
      limit.notch.style.setProperty("--at", at);
      limit.tick.style.setProperty("--at", at);
      limit.value.textContent = `${Math.round(value)}%`;
    }
    r.down.hidden = !showTarget && !showShutdown;

    const limits = [showTarget && `target ${Math.round(slotSoc)}%`, showShutdown && `shutdown ${Math.round(shutdown)}%`];
    r.card.setAttribute("aria-label", [name, shown, statusText, runtime?.text, ...limits].filter(Boolean).join(", "));
    this._layout();
  }

  // Layout needs the card's width, so it runs again whenever the card is resized.
  // Hidden cards have no width yet and keep the layout they have.
  _layout() {
    const r = this._r;
    const width = this.clientWidth;
    if (!r || !width) return;
    r.card.classList.toggle("wide", width >= WIDE_PX);

    // Labels named when they fit; numbers only when not; the target above the
    // battery when even the numbers would collide.
    const { target, shutdown } = r;
    r.down.append(target.tick);
    target.notch.className = "notch down";
    r.up.classList.remove("used");
    for (const row of [r.down, r.up]) row.classList.remove("bare");
    if (target.tick.hidden || shutdown.tick.hidden) return;
    if (!overlap(target.tick, shutdown.tick)) return;
    r.down.classList.add("bare");
    if (!overlap(target.tick, shutdown.tick)) return;
    r.down.classList.remove("bare");
    r.up.append(target.tick);
    r.up.classList.add("used");
    target.notch.className = "notch up";
  }
}

if (!customElements.get(TYPE)) {
  customElements.define(TYPE, BatteryCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: TYPE,
    name: "Deye Local Battery",
    description: "The battery's state of charge as a battery that fills and changes colour, with charging or discharging power and a runtime estimate.",
    documentationURL: "https://github.com/maxbanton/hass-deye-local#battery-card",
    preview: true,
  });
}
