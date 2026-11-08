// Rules of the battery card, run with `node --test tests/js`.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  activeSlot,
  batteryMode,
  durationParts,
  levelColor,
  runtime,
  shownLimits,
  target,
  totalCapacity,
} from "../../custom_components/deye_local/frontend/battery-card-logic.js";

const slots = (batt, gridCharge = true) =>
  ["01:00", "05:00", "09:00", "13:00", "17:00", "21:00"].map((time) => ({ time, batt, grid_charge: gridCharge }));
const at = (hh, mm = 0) => hh * 60 + mm;
// 200 Ah at 52.8 V: 10.56 kWh, so 1 % is 105.6 Wh.
const battery = { capacity: 200, voltage: 52.8, shutdown: 10 };

describe("batteryMode", () => {
  test("a few tens of watts either way is idle", () => {
    assert.equal(batteryMode(80, -27), "idle");
    assert.equal(batteryMode(80, 30), "idle");
    assert.equal(batteryMode(80, -49), "idle");
  });
  test("negative power charges, positive discharges", () => {
    assert.equal(batteryMode(80, -200), "charging");
    assert.equal(batteryMode(45, 480), "discharging");
  });
  test("no reading means no mode", () => {
    assert.equal(batteryMode(null, 300), null);
    assert.equal(batteryMode(80, null), null);
  });
});

describe("activeSlot", () => {
  const table = slots(80).map((slot, i) => ({ ...slot, batt: 10 * (i + 1) }));
  test("the last slot that has started", () => {
    assert.equal(activeSlot(table, at(9)).batt, 30);
    assert.equal(activeSlot(table, at(12, 59)).batt, 30);
    assert.equal(activeSlot(table, at(23, 30)).batt, 60);
  });
  test("before the first slot, the last one of the day before is in force", () => {
    assert.equal(activeSlot(table, at(0, 30)).batt, 60);
  });
  test("slots without a readable time are skipped", () => {
    assert.equal(activeSlot([{ time: "", batt: 1 }, { time: "02:00", batt: 2 }], at(3)).batt, 2);
    assert.equal(activeSlot([], at(3)), null);
    assert.equal(activeSlot(undefined, at(3)), null);
  });
});

describe("target", () => {
  const slot = { batt: 80, grid_charge: true };
  test("grid charging stops at the slot's SOC", () => {
    assert.equal(target({ mode: "charging", soc: 62, slot }), 80);
  });
  test("past the slot's SOC, or without grid charge, charging runs to full", () => {
    assert.equal(target({ mode: "charging", soc: 85, slot }), 100);
    assert.equal(target({ mode: "charging", soc: 62, slot: { batt: 80, grid_charge: false } }), 100);
    assert.equal(target({ mode: "charging", soc: 62, slot: null }), 100);
  });
  test("on grid the battery stops at the slot's SOC, off grid at the shutdown SOC", () => {
    assert.equal(target({ mode: "discharging", soc: 90, slot, shutdown: 10, gridHz: 50 }), 80);
    assert.equal(target({ mode: "discharging", soc: 90, slot, shutdown: 10, gridHz: 0 }), 10);
  });
  test("without a grid frequency reading it is treated as off grid", () => {
    assert.equal(target({ mode: "discharging", soc: 90, slot, shutdown: 10, gridHz: null }), 10);
  });
  test("a slot SOC below the shutdown SOC does not lower the floor", () => {
    assert.equal(target({ mode: "discharging", soc: 90, slot: { batt: 5 }, shutdown: 10, gridHz: 50 }), 10);
  });
  test("without a shutdown SOC the floor is 0 %", () => {
    assert.equal(target({ mode: "discharging", soc: 90, slot: null, shutdown: null, gridHz: 0 }), 0);
  });
});

describe("runtime", () => {
  const slot = { batt: 80, grid_charge: true };
  test("grid charging to the slot's SOC", () => {
    const r = runtime({ ...battery, mode: "charging", soc: 62, power: -2400, slot, gridHz: 50 });
    assert.equal(r.label, "80% in");
    assert.equal(r.text, "80% in ~50 min");
  });
  test("charging to full", () => {
    assert.equal(runtime({ ...battery, mode: "charging", soc: 80, power: -900, slot: null, gridHz: 50 }).text, "Full in ~2 h 20 min");
  });
  test("discharging during an outage lasts to the shutdown SOC", () => {
    const r = runtime({ ...battery, mode: "discharging", soc: 45, power: 480, slot, gridHz: 0 });
    assert.equal(r.label, "Lasts");
    assert.equal(r.text, "Lasts ~7 h 40 min");
  });
  test("discharging on grid runs to the slot's SOC", () => {
    assert.equal(runtime({ ...battery, mode: "discharging", soc: 85, power: 475, slot, gridHz: 50 }).text, "80% in ~1 h 5 min");
  });
  test("nothing when the battery is already at or past where it is heading", () => {
    assert.equal(runtime({ ...battery, mode: "charging", soc: 100, power: -300, slot: null }), null);
    assert.equal(runtime({ ...battery, mode: "discharging", soc: 9, power: 300, slot: null, gridHz: 0 }), null);
    assert.equal(runtime({ ...battery, mode: "discharging", soc: 60, power: 475, slot, gridHz: 50 }), null);
  });
  test("a top-up trickle at the target does not become a charge time of days", () => {
    // 20 % at 70 W would be about 30 hours.
    assert.equal(runtime({ ...battery, mode: "charging", soc: 80, power: -70, slot, gridHz: 50 }), null);
  });
  test("a long discharge on a small load is shown in days", () => {
    assert.equal(runtime({ ...battery, mode: "discharging", soc: 80, power: 60, slot: null, gridHz: 0 }).text, "Lasts ~5 days");
  });
  test("nothing without capacity, voltage or a flow", () => {
    assert.equal(runtime({ ...battery, capacity: null, mode: "discharging", soc: 45, power: 480, gridHz: 0 }), null);
    assert.equal(runtime({ ...battery, voltage: null, mode: "discharging", soc: 45, power: 480, gridHz: 0 }), null);
    assert.equal(runtime({ ...battery, mode: "idle", soc: 45, power: 10 }), null);
  });
});

describe("durationParts", () => {
  test("minutes round to 5 and never show 0", () => {
    assert.deepEqual(durationParts(0.01), [[5, "min"]]);
    assert.deepEqual(durationParts(0.23), [[15, "min"]]);
  });
  test("hours and minutes up to 10 hours", () => {
    assert.deepEqual(durationParts(1.37), [[1, "h"], [20, "min"]]);
    assert.deepEqual(durationParts(2), [[2, "h"]]);
  });
  test("whole hours from 10 hours, days from 2 days", () => {
    assert.deepEqual(durationParts(13.3), [[13, "h"]]);
    assert.deepEqual(durationParts(47.9), [[48, "h"]]);
    assert.deepEqual(durationParts(123), [[5, "days"]]);
  });
});

describe("levelColor", () => {
  test("default levels", () => {
    assert.equal(levelColor(15), "red");
    assert.equal(levelColor(20), "amber");
    assert.equal(levelColor(49), "amber");
    assert.equal(levelColor(50), "green");
  });
  test("custom levels, and no amber when both are equal", () => {
    assert.equal(levelColor(25, 30, 60), "red");
    assert.equal(levelColor(45, 30, 60), "amber");
    assert.equal(levelColor(40, 15, 15), "green");
  });
});

describe("shownLimits", () => {
  test("both limits inside the battery are marked", () => {
    assert.deepEqual(shownLimits(80, 10), { target: true, shutdown: true });
  });
  test("a limit at 0 % or 100 % is not marked", () => {
    assert.deepEqual(shownLimits(100, 0), { target: false, shutdown: false });
  });
  test("a target equal to the shutdown SOC is marked once", () => {
    assert.deepEqual(shownLimits(10, 10), { target: false, shutdown: true });
  });
  test("an unknown limit is not marked", () => {
    assert.deepEqual(shownLimits(null, null), { target: false, shutdown: false });
  });
});

describe("totalCapacity", () => {
  test("the configured capacity wins", () => {
    assert.equal(totalCapacity(150, [100, 100]), 150);
  });
  test("otherwise the modules add up", () => {
    assert.equal(totalCapacity(undefined, [100, 100]), 200);
  });
  test("unknown when a module has not reported or there are none", () => {
    assert.equal(totalCapacity(undefined, [100, null]), null);
    assert.equal(totalCapacity(undefined, []), null);
  });
});
