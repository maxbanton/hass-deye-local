// What the battery card shows, worked out from plain values: no DOM and no Home
// Assistant objects, so every rule can be tested on its own.

// Battery power is negative while the battery charges. An idle battery still shows a
// few tens of watts either way, which would make runtimes of days; below this it is idle.
export const IDLE_WATTS = 50;
export const RED_BELOW = 20;
export const AMBER_BELOW = 50;
// Below this the inverter is off grid: it reports no frequency without a grid.
export const GRID_HZ = 40;
// Longer charge estimates are not shown.
export const MAX_CHARGE_HOURS = 24;

export function numberOrNull(value) {
  const n = Number(value);
  return value !== undefined && value !== null && value !== "" && Number.isFinite(n) ? n : null;
}

export function clockMinutes(value) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

// Whole hours and minutes in 5 minute steps; past 10 hours the minutes are noise,
// and past two days so are the hours.
export function durationParts(hours) {
  const minutes = Math.max(5, Math.round((hours * 60) / 5) * 5);
  if (minutes < 60) return [[minutes, "min"]];
  if (hours >= 48) return [[Math.round(hours / 24), "days"]];
  if (hours >= 10) return [[Math.round(hours), "h"]];
  const rest = minutes % 60;
  return rest ? [[Math.floor(minutes / 60), "h"], [rest, "min"]] : [[minutes / 60, "h"]];
}

// The slot in force now: the last one that started today, or else the last of the
// day before, since the table wraps around midnight.
export function activeSlot(schedule, now) {
  const slots = (Array.isArray(schedule) ? schedule : [])
    .map((slot) => ({ slot, start: clockMinutes(slot?.time) }))
    .filter((s) => s.start !== null);
  if (!slots.length) return null;
  const started = slots.filter((s) => s.start <= now);
  const pick = (list) => list.reduce((a, b) => (b.start > a.start ? b : a));
  return pick(started.length ? started : slots).slot;
}

export function batteryMode(soc, power) {
  if (soc === null || power === null) return null;
  if (Math.abs(power) < IDLE_WATTS) return "idle";
  return power < 0 ? "charging" : "discharging";
}

export function levelColor(level, redBelow = RED_BELOW, amberBelow = AMBER_BELOW) {
  if (level < redBelow) return "red";
  if (level < amberBelow) return "amber";
  return "green";
}

// The configured capacity, or else the battery modules' capacities added up, or null
// when any module has not reported one.
export function totalCapacity(configured, modules) {
  const own = numberOrNull(configured);
  if (own) return own;
  return modules.length && modules.every((v) => v > 0) ? modules.reduce((a, b) => a + b, 0) : null;
}

// The SOC the battery is heading for. The time of use slot's SOC is the grid charge
// target, and while the grid is up the battery does not discharge below it. Off grid
// it runs down to the shutdown SOC.
export function target({ mode, soc, slot, shutdown, gridHz }) {
  const slotSoc = numberOrNull(slot?.batt);
  if (mode === "charging") {
    return slot?.grid_charge && slotSoc !== null && slotSoc > soc ? slotSoc : 100;
  }
  const floor = shutdown ?? 0;
  const onGrid = (gridHz ?? 0) >= GRID_HZ;
  return onGrid && slotSoc !== null && slotSoc > floor ? slotSoc : floor;
}

// Rough, like the inverter app's: linear in SOC, at the present voltage and power.
// Returns the headline label, the duration parts and the one line text, or null.
export function runtime({ mode, soc, power, capacity, voltage, slot, shutdown, gridHz }) {
  if (mode !== "charging" && mode !== "discharging") return null;
  if (!capacity || !voltage || !power) return null;
  const goal = target({ mode, soc, slot, shutdown, gridHz });
  if ((mode === "charging" && soc >= goal) || (mode === "discharging" && soc <= goal)) return null;
  const hours = ((Math.abs(goal - soc) / 100) * capacity * voltage) / Math.abs(power);
  // Charging that slow is a trickle, not something to plan around; a long
  // discharge on a small load is real and stays.
  if (mode === "charging" && hours > MAX_CHARGE_HOURS) return null;
  const parts = durationParts(hours);
  // "Lasts" only when the battery runs to its end; on grid the inverter switches over at the slot SOC.
  let label;
  if (mode === "discharging" && goal <= (shutdown ?? 0)) label = "Lasts";
  else label = goal >= 100 ? "Full in" : `${Math.round(goal)}% in`;
  return { label, parts, text: `${label} ~${parts.map(([n, u]) => `${n} ${u}`).join(" ")}` };
}

// Which limits to mark. A limit at either end of the battery says nothing the
// battery itself does not, and a target equal to the shutdown SOC is marked once.
export function shownLimits(slotSoc, shutdown) {
  const inside = (v) => v !== null && v > 0 && v < 100;
  return {
    shutdown: inside(shutdown),
    target: inside(slotSoc) && slotSoc !== shutdown,
  };
}
