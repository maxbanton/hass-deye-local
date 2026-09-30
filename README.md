# Deye Local for Home Assistant

Home Assistant integration for Deye hybrid inverters that reads the inverter
locally over Bluetooth, through the WiBLE data logger that is already plugged
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
  every few seconds; values arrive 4 to 11 seconds old (6 seconds typically),
  compared with 3 to 5 minutes through the cloud.
- **Works without the internet.** Useful exactly when the grid or the connection
  is down.
- **Inverter state, alarms and fault codes.** A fault such as `F13` (working mode
  changed) shows up in Home Assistant within seconds, with its description as an
  attribute, so you can alert on it.
- **Battery BMS data**: BMS SOC, voltage and current, the charge and discharge
  limits the BMS asks for, and per-module data for each battery.
- **Energy counters** with the right state classes for the Energy dashboard.
- **Read only.** This version never changes a setting on the inverter.

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

The logger accepts a single Bluetooth connection. While Home Assistant is
connected, the Deye app can still use the cloud as usual, but its local
Bluetooth mode cannot connect. When you need the app's Bluetooth mode on site,
disable the Deye Local entry (**Settings > Devices & Services > Deye Local**,
three-dot menu, **Disable**), which releases the logger, and enable it again
afterwards. The logger keeps uploading to the Deye Cloud over Wi-Fi either way
(verified over a continuous 15 hour session with no upload gaps).

## Supported inverters

The integration reads the inverter's family from register 0 during setup and
picks the matching register map.

| Family | Models | Status |
|--------|--------|--------|
| Single phase hybrid | SUN-*K-SG0*LP1 | Supported, verified on hardware |
| Three phase hybrid, low and high voltage | SUN-*K-SG0*LP3, SUN-*K-SG0*HP3 | Experimental |
| String, micro, high voltage three phase, off grid | | Recognised, not mapped yet |

**Experimental** means the register map follows Deye's protocol documents and
two independent open source implementations, but has not been confirmed on real
hardware by this project yet.
Values are read only, and a repair notice asks you to report anything that looks
wrong.

**Recognised, not mapped yet** means setup still succeeds and the device shows
its type and identity, so you can download the diagnostics and help add it (see
below).

## Installation (HACS)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/maxbanton/hass-deye-local` with category **Integration**.
3. Install **Deye Local** and restart Home Assistant.
4. Once the logger is in range of your adapter or proxy, Home Assistant shows it
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
| Poll interval | 10 s | 10 to 300 s |
| Keep the Bluetooth connection open | On | On or off |

The logger's cache refreshes every few seconds, so 10 seconds is the fastest
useful interval. Each poll reads every mapped register in small blocks over the
existing connection, which takes about 2 to 4 seconds depending on how many
battery modules there are.

Keeping the connection open avoids reconnecting, which is the slowest and least
reliable part of a Bluetooth exchange. Some users report loggers that stop
uploading to the Deye Cloud while a session stays open; if yours does, turn the
option off and the integration connects for each poll and releases the logger in
between. Expect slower polls and the occasional failed connection in that mode,
so a longer poll interval (30 to 60 seconds) suits it better.

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
are available but disabled; enable any you need from the entity settings.

Power and current are signed: battery power and current are negative while the
battery charges; grid power is positive while importing.

At a 10 second interval power values change on almost every poll. If your
database grows more than you like, exclude the high frequency sensors you do not
need from the recorder, or raise the poll interval.

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
3. Open an [issue](https://github.com/maxbanton/hass-deye-local/issues) with both.

## Relation to Deye Cloud

[Deye Cloud](https://github.com/maxbanton/hass-deye-cloud) reads the same
inverter through Deye's official cloud API. The two run side by side without
interfering: the logger serves this integration over Bluetooth and keeps
uploading to the cloud over Wi-Fi. The cloud remains useful for access away from
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
- You use it entirely at your own risk and responsibility. The author and
  contributors are not liable for any damage to inverters, batteries, other
  equipment or property, for personal injury, data loss, loss of warranty,
  financial loss, or any other direct or indirect consequence of installing or
  using it.

## License

MIT, see [LICENSE](LICENSE).
