"""Constants for Deye Local."""
from __future__ import annotations

DOMAIN = "deye_local"
MANUFACTURER = "Deye"

# GATT layout of the WiBLE data logger. Commands are ASCII lines written to the
# command characteristic (write with response); replies arrive as notifications.
SERVICE_UUID = "00000922-0000-1000-8000-00805f9b34fb"
COMMAND_CHAR = "0000fec7-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000fed8-0000-1000-8000-00805f9b34fb"

CONF_DEVICE_TYPE = "device_type"
CONF_SERIAL = "serial"

# The logger answers reads from a cache the inverter refreshes every few seconds,
# so polling faster than this only adds Bluetooth traffic and database writes.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 300

# Some loggers stop uploading to the cloud while a Bluetooth session stays open;
# turning this off connects for each poll and releases the logger in between.
CONF_KEEP_CONNECTED = "keep_connected"
DEFAULT_KEEP_CONNECTED = True

# How long last good values survive failed polls, so one dropped exchange does
# not blank every entity.
STALE_TIMEOUT = 60  # seconds

REPLY_TIMEOUT = 5.0

# How often the battery module slots are re-read to notice added or removed modules.
BATTERY_SCAN_INTERVAL = 300  # seconds

# The logger does not answer large reads.
MAX_BLOCK = 16
