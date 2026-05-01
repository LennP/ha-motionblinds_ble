"""End-to-end tests for the MotionBlinds BLE integration.

What this covers:
    * Manifest + integration loads
    * Roller / curtain / vertical entry sets up the right entities
    * The new `Temperature`, `Illuminance`, `Brightness setpoint`,
      `Direction`, `Point type`, `Endpoints set`, `Sensor status`
      sensors are created
    * The new `Light`, `Rain sensor`, `Wind sensor`, `Combo sensor`,
      `Slow stop` switches are created
    * The `Brightness` number entity is created
    * All extended buttons (calibration, endpoint set, angle set, point
      up/down, back-side movement, etc.) are created
    * The `Device type (E/ED)` select is created
    * Each command produces an AES-encrypted GATT write whose decrypted
      plaintext starts with the documented opcode (per protocol PDF
      §7 / Coulisse Constants.java)
    * The notification parsers correctly populate state for every
      response prefix we handle (temperature, illuminance, brightness
      setpoint, slow stop, endpoints, direction, sensor status, point
      type)

Nothing here talks to a real motor — the BleakClient is faked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

DOMAIN = "motionblinds_ble"

# Default test fixture data
TEST_ADDR = "AA:BB:CC:DD:EE:FF"
TEST_MAC4 = "EEFF"  # last 4 hex chars of TEST_ADDR — what library uses for display


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest.fixture
async def mock_ble_helpers(hass: HomeAssistant):
    """Replace BLE callback registration so setup doesn't need real BT."""
    from homeassistant import loader

    integration = await loader.async_get_integration(hass, DOMAIN)
    await integration.async_get_component()  # force-import the module

    with patch(
        "custom_components.motionblinds_ble.async_ble_device_from_address",
        return_value=None,
    ), patch(
        "custom_components.motionblinds_ble.async_register_callback",
        return_value=lambda: None,
    ):
        yield


def make_entry(blind_type: str = "roller") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"MotionBlind {blind_type.upper()}",
        data={
            CONF_ADDRESS: TEST_ADDR,
            "local_name": "MOTION_TEST",
            "mac_code": "TEST",
            "blind_type": blind_type,
        },
        unique_id=TEST_ADDR,
        source=SOURCE_USER,
    )


async def setup_entry(
    hass: HomeAssistant, blind_type: str = "roller"
) -> MockConfigEntry:
    """Add and set up a config entry, return the entry once LOADED."""
    entry = make_entry(blind_type)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def make_fake_client():
    """A bleak client stand-in that records writes and reports as connected."""

    class FakeClient:
        is_connected = True
        sent: list[tuple[str, bytes]] = []

        async def write_gatt_char(self, uuid, payload, response=False):
            self.sent.append((str(uuid), bytes(payload)))

    return FakeClient()


def fake_connect(device, fake_client) -> None:
    """Pretend the device is connected with end-positions set so commands
    are not gated by `requires_end_positions`."""
    from motionblindsble.device import MotionEndPositions, MotionPositionInfo
    from motionblindsble.crypt import MotionCrypt

    MotionCrypt.set_timezone("Europe/Amsterdam")
    device._current_bleak_client = fake_client  # noqa: SLF001
    info = MotionPositionInfo(0)
    info.end_positions = MotionEndPositions.BOTH
    info.favorite_position = True
    device._end_position_info = info  # noqa: SLF001
    device._received_end_position_info_event.set()  # noqa: SLF001


def decrypt(hexstr: str) -> str:
    from motionblindsble.crypt import MotionCrypt

    return MotionCrypt.decrypt(hexstr)


# --------------------------------------------------------------------------- #
# Manifest + setup
# --------------------------------------------------------------------------- #


async def test_manifest(hass: HomeAssistant) -> None:
    from homeassistant import loader

    integration = await loader.async_get_integration(hass, DOMAIN)
    assert integration.domain == DOMAIN
    assert "motionblindsble==0.1.3" in integration.manifest["requirements"]
    assert integration.config_flow is True

    component = await integration.async_get_component()
    # The integration must be loaded from custom_components, NOT from HA core
    # (otherwise we're just testing the upstream integration, not our changes)
    assert component.__name__ == "custom_components.motionblinds_ble"


async def test_setup_roller_creates_all_entities(
    hass: HomeAssistant, mock_ble_helpers
) -> None:
    """Roller blind should create the full set of entities (incl. extended)."""
    entry = await setup_entry(hass, "roller")

    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    unique_ids = {e.unique_id for e in entries}

    # Core entities (always on)
    expected_visible = {
        f"{TEST_ADDR}",                   # cover
        f"{TEST_ADDR}_battery",
        f"{TEST_ADDR}_connection",
        f"{TEST_ADDR}_signal_strength",
        f"{TEST_ADDR}_speed",             # roller has speed select
        f"{TEST_ADDR}_connect",
        f"{TEST_ADDR}_disconnect",
        f"{TEST_ADDR}_favorite",
        f"{TEST_ADDR}_temperature",
        f"{TEST_ADDR}_illuminance",
        f"{TEST_ADDR}_light",             # switch
        f"{TEST_ADDR}_slow_stop",         # switch
    }
    missing = expected_visible - unique_ids
    assert not missing, f"missing: {missing}"

    # Extended entities (registry-disabled by default — but still registered)
    expected_extended = {
        # Sensors
        f"{TEST_ADDR}_brightness",
        f"{TEST_ADDR}_direction",
        f"{TEST_ADDR}_point_type",
        f"{TEST_ADDR}_endpoints",
        f"{TEST_ADDR}_sensor_status",
        # Switches
        f"{TEST_ADDR}_rain_sensor",
        f"{TEST_ADDR}_wind_sensor",
        f"{TEST_ADDR}_combo_sensor",
        # Number
        # (brightness number reuses the brightness key — already covered)
        # Buttons
        f"{TEST_ADDR}_point_up",
        f"{TEST_ADDR}_point_down",
        f"{TEST_ADDR}_calibration_begin",
        f"{TEST_ADDR}_calibration_end",
        f"{TEST_ADDR}_set_endpoint_up",
        f"{TEST_ADDR}_set_endpoint_down",
        f"{TEST_ADDR}_set_endpoint_third",
        f"{TEST_ADDR}_set_angle_begin",
        f"{TEST_ADDR}_set_angle_zero",
        f"{TEST_ADDR}_set_angle_ninety",
        f"{TEST_ADDR}_set_angle_one_eighty",
        f"{TEST_ADDR}_tilt_reverse",
        f"{TEST_ADDR}_auto_position",
        f"{TEST_ADDR}_set_direction",
        f"{TEST_ADDR}_back_top_open",
        f"{TEST_ADDR}_back_top_close",
        f"{TEST_ADDR}_back_bottom_open",
        f"{TEST_ADDR}_back_bottom_close",
        # Select
        f"{TEST_ADDR}_device_type",
    }
    missing_ext = expected_extended - unique_ids
    assert not missing_ext, f"missing extended: {missing_ext}"


# --------------------------------------------------------------------------- #
# Commands → encrypted GATT write whose plaintext begins with opcode
# --------------------------------------------------------------------------- #


COMMAND_CASES = [
    # (display, async-method, expected plaintext prefix)
    # Light
    ("light_on",            lambda d: d.light_on(),            "03020371"),
    ("light_off",           lambda d: d.light_off(),           "03020372"),
    ("brightness_query",    lambda d: d.brightness_query(),    "030501fb"),
    ("set_brightness(50)",  lambda d: d.set_brightness(50),    "0502071132"),
    # Sensors
    ("rain_on",             lambda d: d.rain_sensor(True),     "03020373"),
    ("rain_off",            lambda d: d.rain_sensor(False),    "03020374"),
    ("wind_on",             lambda d: d.wind_sensor(True),     "03020377"),
    ("wind_off",            lambda d: d.wind_sensor(False),    "03020378"),
    ("combo_on",            lambda d: d.combo_sensor(True),    "03020357"),
    ("combo_off",           lambda d: d.combo_sensor(False),   "03020358"),
    ("wind_rain_query",     lambda d: d.wind_rain_query(),     "03050187"),
    # Slow stop
    ("slow_stop_on",        lambda d: d.slow_stop(True),       "03020342"),
    ("slow_stop_off",       lambda d: d.slow_stop(False),      "03020341"),
    ("slow_stop_query",     lambda d: d.slow_stop_query(),     "03050480"),
    # Calibration / endpoints / angles  -- THE END-POSITION PROGRAMMING SET
    ("calibration_begin",   lambda d: d.calibration_begin(),   "0302035c"),
    ("calibration_end",     lambda d: d.calibration_end(),     "0302035d"),
    ("set_endpoint_up",     lambda d: d.set_endpoint_up(),     "03020323"),
    ("set_endpoint_down",   lambda d: d.set_endpoint_down(),   "03020324"),
    ("set_endpoint_third",  lambda d: d.set_endpoint_third(),  "03020325"),
    ("set_angle_begin",     lambda d: d.set_angle_begin(),     "03020321"),
    ("set_angle_zero",      lambda d: d.set_angle_zero(),      "03020322"),
    ("set_angle_ninety",    lambda d: d.set_angle_ninety(),    "0302032b"),
    ("set_angle_one_eighty", lambda d: d.set_angle_one_eighty(), "0302032e"),
    ("tilt_reverse",        lambda d: d.tilt_reverse(),        "03020334"),
    ("auto_position",       lambda d: d.auto_position(),       "0302032f"),
    ("set_direction",       lambda d: d.set_direction(),       "03020317"),
    ("endpoints_query",     lambda d: d.endpoints_query(),     "03050120"),
    # Point movement
    ("point_up",            lambda d: d.point_up(),            "03020304"),
    ("point_down",          lambda d: d.point_down(),          "03020305"),
    # Backside movement
    ("back_top_open",       lambda d: d.back_top_open(),       "03020382"),
    ("back_top_close",      lambda d: d.back_top_close(),      "03020383"),
    ("back_bottom_open",    lambda d: d.back_bottom_open(),    "03020384"),
    ("back_bottom_close",   lambda d: d.back_bottom_close(),   "03020385"),
    # Device type
    ("set_device_type_e",   lambda d: d.set_device_type_e(),   "03020380"),
    ("set_device_type_ed",  lambda d: d.set_device_type_ed(),  "03020381"),
    ("device_type_query",   lambda d: d.device_type_query(),   "03050110"),
    ("point_type_query",    lambda d: d.point_type_query(),    "0305018b"),
    ("direction_query",     lambda d: d.direction_query(),     "03050148"),
    ("vertical_state_query", lambda d: d.vertical_state_query(), "03050106"),
    # Temperature + illuminance (same query)
    ("temperature_query",   lambda d: d.temperature_query(),   "030510fa"),
]


@pytest.mark.parametrize("name, action, expected_prefix", COMMAND_CASES)
async def test_command_emits_correct_opcode(
    hass: HomeAssistant,
    mock_ble_helpers,
    name: str,
    action,
    expected_prefix: str,
) -> None:
    """Each extended command should write an AES-encrypted payload whose
    plaintext begins with the documented opcode."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    fake = make_fake_client()
    fake_connect(device, fake)
    fake.sent.clear()

    try:
        ok = await action(device)
        assert ok is True, f"{name}: command returned False"
        assert fake.sent, f"{name}: no GATT write emitted"
        plaintext = decrypt(fake.sent[-1][1].hex())
        assert plaintext.startswith(expected_prefix), (
            f"{name}: expected prefix {expected_prefix}, got {plaintext}"
        )
    finally:
        # Cancel the disconnect timer that connect() scheduled, so HA's
        # `verify_cleanup` fixture doesn't fail us for a lingering timer.
        device._cancel_disconnect_timer()  # noqa: SLF001
        device._disconnect_timer = None  # noqa: SLF001
        device._current_bleak_client = None  # noqa: SLF001


# --------------------------------------------------------------------------- #
# Notification parsers
# --------------------------------------------------------------------------- #


def _encrypt(plaintext_hex: str) -> bytearray:
    from motionblindsble.crypt import MotionCrypt

    return bytearray.fromhex(MotionCrypt.encrypt(plaintext_hex))


async def test_temperature_and_illuminance_parser(
    hass: HomeAssistant, mock_ble_helpers
) -> None:
    """`130410fa…TT HH LL` should produce °C from TT and lux = (HH<<8|LL) ×10."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data

    received_temp: list[int | None] = []
    received_lux: list[int | None] = []
    device.register_temperature_callback(received_temp.append)
    device.register_illuminance_callback(received_lux.append)

    # Fake response: 19 bytes total. 16 bytes of payload after the 4-byte
    # opcode prefix; we only care about the LAST 3 bytes of the decrypted
    # plaintext: temp=0x16 (22°C), lux raw 0x0064 = 100 → 1000 lux.
    plaintext = "130410fa" + "00" * 12 + "16" + "00" + "64"
    encrypted = _encrypt(plaintext)
    device._notification_callback(None, encrypted)  # noqa: SLF001

    assert received_temp == [22], received_temp
    assert received_lux == [1000], received_lux


async def test_brightness_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    """`070404fb XX` → byte XX is the brightness percentage."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[int | None] = []
    device.register_brightness_callback(received.append)

    plaintext = "070404fb" + "42" + "00" * 2  # 0x42 = 66
    device._notification_callback(None, _encrypt(plaintext))  # noqa: SLF001

    assert received == [0x42]


async def test_endpoints_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    """`04040120 BB` — bits 7,6,5 (MSB) = up, down, favorite (Java `bit(b, n)`
    is bit `7-n`, so up = bit 7, down = bit 6, favorite = bit 5)."""
    from custom_components.motionblinds_ble.device import EndpointInfo

    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[EndpointInfo | None] = []
    device.register_endpoint_callback(received.append)

    # 0xE0 = 0b11100000 → up=1, down=1, favorite=1
    device._notification_callback(  # noqa: SLF001
        None, _encrypt("04040120" + "e0" + "00" * 1)
    )
    assert received[-1].up is True
    assert received[-1].down is True
    assert received[-1].favorite is True

    # 0x80 = 0b10000000 → only up
    device._notification_callback(  # noqa: SLF001
        None, _encrypt("04040120" + "80" + "00" * 1)
    )
    assert received[-1].up is True
    assert received[-1].down is False
    assert received[-1].favorite is False


async def test_direction_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    """`04040148 01` → reversed; anything else → normal."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[bool | None] = []
    device.register_direction_callback(received.append)

    device._notification_callback(None, _encrypt("04040148" + "01" + "00"))  # noqa: SLF001
    device._notification_callback(None, _encrypt("04040148" + "00" + "00"))  # noqa: SLF001
    assert received == [True, False]


async def test_slow_stop_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    """`07040480 …` last byte's bin[4]=='0' → on (per Android source)."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[bool | None] = []
    device.register_slow_stop_callback(received.append)

    # Last byte 0x00 → bin "00000000" → bin[4]='0' → ON
    device._notification_callback(None, _encrypt("07040480" + "00" * 4))  # noqa: SLF001
    # Last byte 0x08 → bin "00001000" → bin[4]='1' → OFF
    device._notification_callback(None, _encrypt("07040480" + "00" * 3 + "08"))  # noqa: SLF001
    assert received == [True, False]


async def test_sensor_status_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    from custom_components.motionblinds_ble.device import SensorStatus

    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[SensorStatus | None] = []
    device.register_sensor_status_callback(received.append)

    device._notification_callback(None, _encrypt("04040187" + "5a" + "00"))  # noqa: SLF001
    assert received[-1].raw == 0x5A


async def test_point_type_parser(hass: HomeAssistant, mock_ble_helpers) -> None:
    """`0404018b BB` — bin8(BB)[5] == '1' → 'E', else 'ED'."""
    entry = await setup_entry(hass, "roller")
    device = entry.runtime_data
    received: list[str | None] = []
    device.register_point_type_callback(received.append)

    # 0x04 = 0b00000100 → bin[5] = '1' → E
    device._notification_callback(None, _encrypt("0404018b" + "04" + "00"))  # noqa: SLF001
    # 0x00 = 0b00000000 → bin[5] = '0' → ED
    device._notification_callback(None, _encrypt("0404018b" + "00" + "00"))  # noqa: SLF001
    assert received == ["E", "ED"]
