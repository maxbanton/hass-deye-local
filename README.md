# Deye Local for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/maxbanton/hass-deye-local)](https://github.com/maxbanton/hass-deye-local/releases)
[![Tests](https://github.com/maxbanton/hass-deye-local/actions/workflows/tests.yml/badge.svg)](https://github.com/maxbanton/hass-deye-local/actions/workflows/tests.yml)
[![Validate](https://github.com/maxbanton/hass-deye-local/actions/workflows/validate.yml/badge.svg)](https://github.com/maxbanton/hass-deye-local/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/maxbanton/hass-deye-local)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.3%2B-41BDF5.svg)](https://www.home-assistant.io)

Home Assistant integration for Deye hybrid inverters that reads and controls the
inverter locally over Bluetooth, through the WiBLE data logger that is already plugged
into it. No cloud, no internet, no extra wiring.

> [!WARNING]
> This is an unofficial integration built on a protocol Deye does not document
> or support. It talks directly to equipment that controls high voltage and
> stores large amounts of energy. Use it at your own risk: the author accepts no
> responsibility for any damage to the inverter, batteries, other equipment or
> property, for injury, data loss, lost warranty or any other consequence of
> using it. See the [disclaimer](#disclaimer).

## Why this exists

Newer Deye data loggers (the WiBLE generation, firmware `DYDA_WiBLE_*`) close
their local Modbus ports: `8899` and `502` are shut, so the Solarman based
integrations cannot connect, and there is no firmware rollback. That leaves the
Deye Cloud (data 3 to 5 minutes late, quota limited) or extra hardware wired to
the inverter's RS485 port.

The logger does keep one local door open: its Bluetooth link, which the Deye app
uses for commissioning. Over that link the logger forwards Modbus requests to the
inverter and returns the answers. This integration uses exactly that, so any
inverter with a WiBLE logger can be read in Home Assistant with nothing more
than a Bluetooth adapter or an ESPHome Bluetooth proxy in range.

## What it gives you

- **Near real time data.** The logger answers from a cache the inverter refreshes
  every few seconds. Values update every 30 seconds by default, or every 10
  seconds with the connection kept open, compared with 3 to 5 minutes through
  the cloud.
- **Works without the internet.** Useful exactly when the grid or the connection
  is down.
- **Inverter state, alarms and fault codes.** A fault such as `F13` (working mode
  changed) shows up in Home Assistant within seconds, with its description as an
  attribute, so you can alert on it.
- **Battery BMS data**: BMS SOC, voltage and current, the charge and discharge
  limits the BMS asks for, and per-module data for each battery.
- **Energy counters** with the right state classes for the Energy dashboard.
- **Settings you can change** on single phase hybrids: battery charge and
  discharge current, grid charge current, shutdown, restart and low SOC, energy
  pattern, work mode, grid charging, the six time of use slots, max sell and
  zero export power, and grid peak shaving. Low voltage three phase hybrids get
  the time of use switch and slots (experimental). Every change is read back
  from the inverter and reported as an error if it did not stick.

## What you need

The logger has to be within Bluetooth range of Home Assistant. Pick one:

### Option A: a USB Bluetooth adapter

Plug an adapter from the list of known working adapters in Home Assistant's
[Bluetooth documentation](https://www.home-assistant.io/integrations/bluetooth/)
into the machine running Home Assistant. Home Assistant OS already includes the
Linux Bluetooth stack; on a Docker install the host needs BlueZ and the container
needs access to D-Bus.

Put the adapter on a short USB extension cable, away from USB 3 ports and the
computer's metal case. Both drown out 2.4 GHz radios: in testing, an ESP32
plugged straight into a small PC's USB port saw its Wi-Fi drop from -39 dBm to
-88 dBm and lost the nearby access point entirely.

### Option B: an ESP32 as an ESPHome Bluetooth proxy

Any ESP32 (the ESP32-C3 and ESP32-C6 work well) flashed with ESPHome as a
Bluetooth proxy, placed within a few metres of the inverter. It needs active
connections enabled:

```yaml
esp32:
  board: esp32-c3-devkitm-1
  framework:
    type: esp-idf

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
ota:
  - platform: esphome

esp32_ble_tracker:
  scan_parameters:
    active: false

bluetooth_proxy:
  active: true
```

Passive scanning is enough here (it keeps the chip cooler); `bluetooth_proxy:
active: true` is what allows Home Assistant to connect through the proxy. The
proxy also needs decent Wi-Fi, so check its signal after placing it.

### One connection at a time

The logger accepts a single Bluetooth connection, and while that connection
stays open it stops uploading inverter data to the Deye Cloud: the logger still
shows as online, but the inverter and battery values in the cloud and the Deye
app freeze until the connection closes. That is why the integration connects for
each poll and releases the logger in between by default (see [Options](#options)).

The Deye app's local Bluetooth mode needs the logger to itself. When you need it
on site, disable the Deye Local entry (**Settings > Devices & Services > Deye
Local**, three-dot menu, **Disable**), which releases the logger, and enable it
again afterwards.

## Supported inverters

The integration reads the inverter's family from register 0 during setup and
picks the matching register map.

| Family | Models | Status |
|--------|--------|--------|
| Single phase hybrid | `SUN-*K-SG0*LP1`, for example SUN-3.6K-SG03LP1-EU, SUN-6K-SG05LP1-EU, SUN-8K-SG01LP1-EU | Supported, verified on a SUN-6K-SG05LP1-EU-AM2-P |
| Three phase hybrid, low and high voltage | `SUN-*K-SG0*LP3` and `SUN-*K-SG0*HP3`, for example SUN-12K-SG04LP3-EU, SUN-10K-SG01HP3-EU-AM2 | Experimental, reported working on a SUN-10K-SG05LP3-EU-SM2 |
| String, micro, high voltage three phase, off grid | | Recognised, not mapped yet |

Any regional or variant suffix (`-EU`, `-US`, `-AM2`, `-P` and so on) belongs to the
same family as the base model.

**Experimental** means the register map follows Deye's protocol documents and
two independent open source implementations, and user reports confirm it, but it
has not been verified on hardware by this project yet.
Low voltage models (LP3) expose only the time of use switch and slots as
settings; high voltage models (HP3) are read only. A repair notice asks you to
report anything that looks wrong.

**Recognised, not mapped yet** means setup still succeeds and the device shows
its type and identity, so you can download the diagnostics and help add it (see
below).

## Installation (HACS)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=maxbanton&repository=hass-deye-local&category=integration)

Or search in HACS:

1. In HACS, search for **Deye Local**.
2. Install it and restart Home Assistant.
3. Once the logger is in range of your adapter or proxy, Home Assistant shows it
   under **Settings > Devices & Services** as discovered. Click **Configure**.
   You can also add it manually: **Add Integration > Deye Local**, then pick the
   logger from the list.

Setup asks before connecting, then connects once, reads the inverter's family
and serial number, and shows them for confirmation. There are no credentials:
the logger's Bluetooth link needs no pairing.

## Options

Under **Settings > Devices & Services > Deye Local > Configure**:

| Option | Default | Range |
|--------|---------|-------|
| Poll interval | 30 s | 10 to 300 s |
| Keep the Bluetooth connection open | Off | On or off |

By default the integration connects for each poll, reads every mapped register
in small blocks and disconnects again, so the logger keeps uploading to the Deye
Cloud. Connecting is the slowest and least reliable part of a Bluetooth
exchange, which is why the default interval is 30 seconds; an occasional poll
that fails to connect is retried on the next one, and the last values are kept
meanwhile.

Turn **Keep the Bluetooth connection open** on if you do not use the Deye Cloud
or the Deye app away from home. Polls then skip the reconnect and take about 2
to 4 seconds, depending on how many battery modules there are, and since the
logger's cache refreshes every few seconds, 10 seconds becomes a useful
interval. The inverter and battery values in the Deye Cloud stop updating for as
long as the connection stays open.

## Devices and entities

The inverter is one device, and each battery module gets its own device
connected through it:

```
Deye Single phase hybrid        inverter, grid, load, PV, battery totals, BMS
├── Deye battery 1              one device per battery module
└── Deye battery 2
```

- **Inverter**: device state, alarm and fault; battery SOC, voltage, current,
  power and temperature for the whole bank; grid voltage, frequency and power;
  inverter and load power; PV power per string; inverter temperatures; battery,
  grid, load and PV energy counters; the BMS values and the charge and
  discharge limits it asks for; signal strength of the Bluetooth link.
- **Battery modules**: see below.

The essentials are enabled by default. Per string voltages and currents,
generator, output and CT details, the protocol version and the inverter clock
are available but disabled, and so are the BMS values; enable any you need
from the entity settings.

Power and current are signed: battery power and current are negative while the
battery charges; grid power is positive while importing.

At short intervals power values change on almost every poll. If your
database grows more than you like, exclude the high frequency sensors you do not
need from the recorder, or raise the poll interval.

## Settings

Single phase hybrids get these controls on the inverter device:

| Entity | Default |
|--------|---------|
| Battery max charge current, Grid charge current, Energy pattern | enabled, under Controls |
| Battery max discharge current | disabled, under Controls |
| Battery shutdown and restart SOC, Work mode, Time of use, Grid charge | enabled, under Configuration |
| Battery low SOC | disabled, under Configuration |
| TOU slot 1 to 6 time and SOC | enabled, under Configuration |
| Max sell power, Zero export power, Grid peak shaving and its power | disabled, under Configuration |
| TOU slot power, voltage, grid charge and generator charge; Generator charge; Grid charge start SOC | disabled, under Configuration |

Low voltage three phase hybrids (LP3, experimental) get only the Time of use
switch and the TOU slot entities, with the same defaults. Their slot power is
not limited to a rated power yet.

The two charge currents are separate settings on the inverter's screen:
**Battery max charge current** is "Max A Charge" on the first battery setting
page and limits charging from any source; **Grid charge current** is the "A"
value under Grid Charge on the second page and limits charging from the grid.
Grid charging is limited by both.

How changes work:

- The value shown is always the one the inverter reports. Settings are re-read
  every minute, so a change made on the inverter's screen or in the Deye app
  appears in Home Assistant within a minute.
- A change first reads the current value from the inverter, then writes only the
  field you changed. Settings that share a register with others (the time of use
  switch and its weekdays, a slot's grid and generator charging) keep their other
  bits as the inverter has them at that moment.
- After writing, the value is read back until it shows up (the logger may answer
  from its cache for a few seconds). If the inverter does not keep it, the change
  fails with an error in Home Assistant instead of pretending to succeed.
- Limits are only the obvious ones: SOC 0 to 100 %, currents up to 240 A, slot
  and sell power up to the rated power the inverter reports, and slot start times in
  ascending order (each slot runs until the next one starts). Everything else is
  up to the inverter, which rejects what your model or battery does not allow.

Change settings with care: they control how the inverter charges and discharges
the battery and uses the grid.

## Actions

### `deye_local.set_tou_schedule`

Changes several time of use slots in one write, the way the inverter's own Time
Of Use screen saves the whole table. It is faster than changing the slot entities
one by one, and start times can move past each other's old values (each entity
change has to stay between its neighbours).

| Field | Description |
|-------|-------------|
| `device_id` | The inverter. Can be left out when only one is set up. |
| `slots` | Exactly 6 entries, slot 1 to 6. Each can set `time` (HH:MM, when the slot starts), `power` (W), `batt` (target SOC, %), `grid_charge`, `gen` (true/false) and `voltage` (V). |

A field you leave out, or an empty slot `{}`, keeps what the inverter holds at
the moment of the write, so a change made on the inverter's screen since the last
settings read is not undone. Start times are checked against the result: they
have to increase from slot 1 to slot 6. Only the registers that change are
written, then read back like any other setting.

The field names match the `deye_cloud.set_tou_schedule` action of the
[Deye Cloud](https://github.com/maxbanton/hass-deye-cloud) integration.

## Time Of Use card

The integration includes a dashboard card that lays out the time of use table
like the inverter's Work Mode screen and saves your changes in one write. There
is nothing extra to install: Home Assistant loads the card together with the
integration.

![Time Of Use card](https://raw.githubusercontent.com/maxbanton/hass-deye-local/main/docs/tou-card.png)

Add it from the dashboard editor (**Add card**, then search for **Deye Local Time
Of Use**), or in YAML:

```yaml
type: custom:deye-local-tou-card
```

`device` picks the inverter when you have more than one, and `title` replaces the
heading. Both can be set in the card editor.

The integration adds the card to your dashboard resources (**Settings >
Dashboards > ⋮ > Resources**), keeps it on the installed version and removes it
with the last config entry. If your resources are managed in YAML, it loads the
card with Home Assistant's page instead: after installing or updating, reload
the page, or close the Home Assistant app completely and open it again.

- Changes are collected until you press **Save**, then written with
  `deye_local.set_tou_schedule`. Only the fields you changed are sent, so a
  change made on the inverter's screen in the meantime is kept. **Discard**
  drops them.
- Each slot ends where the next one starts, so changing a slot's end time moves
  the next slot's start, as on the inverter. Start times have to stay in order.
- The slot that applies right now is highlighted. Times follow the time format
  in your Home Assistant profile.
- The preview in the card editor is read only, so configuring the card never
  changes the inverter.

The Deye Cloud integration has its own card, **Deye Cloud Time Of Use**, and both
can be used side by side for different inverters.

Example: charge from the grid to 100 % overnight and hold 60 % from 05:00.

```yaml
action: deye_local.set_tou_schedule
data:
  slots:
    - time: "01:00"
      batt: 100
      grid_charge: true
    - time: "05:00"
      batt: 60
    - {}
    - {}
    - {}
    - {}
```

## Battery modules

When the BMS reports per-module data, each module gets its own device
(**Deye battery 1**, **Deye battery 2**, ...) connected through the inverter,
with SOC, voltage, current, temperature, minimum and maximum cell
voltage, the difference between them, state of health and cycle count. Capacity,
cell temperature range and MOS temperature are available but disabled.

Modules are identified by their serial number, so the setup follows changes on
its own:

- A module added to the bank shows up as a new device within five minutes.
- A module moved to another position keeps its device and history.
- A module removed from the bank goes unavailable. Once you are sure it is gone,
  delete its device from the device page to clean up.

The **cell voltage difference** is a useful health indicator. For LiFePO4 cells
it stays small in the middle of the charge range whatever the balance, so check
it near full charge: a spread that grows over months suggests the cells are
drifting apart.

## Adding a new inverter family

If your inverter is experimental or not mapped yet:

1. Open the device under **Settings > Devices & Services > Deye Local** and
   choose **Download diagnostics**. The file includes a dump of the inverter's
   data registers, read over the same Bluetooth link. Serial numbers and
   Bluetooth addresses are removed from it, so it is safe to attach publicly.
2. Note a few values the inverter or the Deye app shows at the same moment
   (battery SOC, battery voltage, grid voltage, today's energy).
3. Open an [Inverter support issue](https://github.com/maxbanton/hass-deye-local/issues/new?template=inverter_support.yml) with both.

## Relation to Deye Cloud

[Deye Cloud](https://github.com/maxbanton/hass-deye-cloud) reads the same
inverter through Deye's official cloud API. The two run side by side as long as
Deye Local releases the logger between polls (the default): the logger serves
this integration over Bluetooth and keeps uploading to the cloud over Wi-Fi.
With the connection kept open, the cloud's inverter values stop updating. The cloud remains useful for access away from
home, for station level figures the cloud computes, and for daily totals that
survive an inverter restart (the inverter resets its own daily counters when it
powers up).

## Credits

- The Bluetooth protocol facts (command channel, `AT+INVDATA` framing, the single
  connection limit and the logger's read cache) were first documented by
  [hacky-swan/deye-bluetooth](https://github.com/hacky-swan/deye-bluetooth).
- Register addresses and scaling follow Deye's Modbus protocol documents, as
  collected and field tested in the inverter definitions of
  [davidrapan/ha-solarman](https://github.com/davidrapan/ha-solarman) (MIT).
  The three phase map was cross-checked against
  [kbialek/deye-inverter-mqtt](https://github.com/kbialek/deye-inverter-mqtt)
  (Apache 2.0). The battery module layout was verified on a live single phase
  system.

This integration is an independent implementation; no code was taken from
either project.

## Removing the integration

1. Go to **Settings > Devices & Services**, open **Deye Local**, and use the
   three-dot menu on the entry to **Delete** it. That releases the logger's
   Bluetooth connection and removes the device and its entities.
2. In HACS, open **Deye Local** and choose **Remove** to delete the files.
3. Restart Home Assistant.

## Requirements

- A Deye inverter with a WiBLE data logger.
- A Bluetooth adapter or ESPHome Bluetooth proxy within range of the logger.
- Home Assistant 2025.3 or newer.

## Disclaimer

This software is provided "as is", without warranty of any kind, express or
implied, including but not limited to the warranties of merchantability, fitness
for a particular purpose and non-infringement. See the [LICENSE](LICENSE).

- It is not affiliated with, endorsed by or supported by Deye. Deye is a
  trademark of its owner.
- It uses an undocumented local protocol of the data logger. Deye may change or
  remove it with any firmware update, and using it may affect your warranty.
- Inverters and batteries operate at dangerous voltages and currents. Nothing in
  this project replaces the manufacturer's documentation, a qualified installer,
  or the protections built into your equipment. Do not rely on it for safety
  critical decisions.
- Settings you change through it are written to the inverter as you set them.
  Wrong values can drain or damage batteries or cut power to your loads; check
  them against your equipment's documentation first.
- You use it entirely at your own risk and responsibility. The author and
  contributors are not liable for any damage to inverters, batteries, other
  equipment or property, for personal injury, data loss, loss of warranty,
  financial loss, or any other direct or indirect consequence of installing or
  using it.

## License

MIT, see [LICENSE](LICENSE).
