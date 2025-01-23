"""Implements Adlar devices."""

from __future__ import annotations

import datetime
import logging

from homeassistant.components.modbus import modbus
from homeassistant.core import HomeAssistant

from .device_map import DEVICE_TYPES, ENTITY_MAP
from .registers import HoldingRegisters, InputRegisters

_LOGGER = logging.getLogger(__name__)


class Device:
    """Nilan Device."""

    def __init__(
        self,
        hass: HomeAssistant,
        name,
        com_type,
        host_ip: str | None,
        host_port,
        slave_id,
    ) -> None:
        """Create new entity of Device Class."""
        self.hass = hass
        self._device_name = name
        self._device_type = ""
        self._device_sw_ver = ""
        self._device_hw_ver = ""
        self._host_ip = host_ip
        self._host_port = host_port
        self._slave_id = int(slave_id)
        self._com_type = com_type
        self._client_config = {
            "name": self._device_name,
            "type": self._com_type,
            "method": "rtu",
            "delay": 0,
            "port": self._host_port,
            "timeout": 1,
            "host": self._host_ip,
            "parity": "E",
            "baudrate": 19200,
            "bytesize": 8,
            "stopbits": 1,
        }
        self._modbus = modbus.ModbusHub(self.hass, self._client_config)
        self._attributes = {}
        self._air_geo_type = 0

    async def setup(self):
        """Modbus and attribute map setup for Nilan Device."""
        _LOGGER.debug("Setup has started")
        hw_type = None
        success = await self._modbus.async_setup()

        if success:
            _LOGGER.debug("Modbus has been setup")
        else:
            await self._modbus.async_close()
            _LOGGER.error("Modbus setup was unsuccessful")
            raise ValueError("Modbus setup was unsuccessful")

        hw_type = await self.get_machine_type()
        _LOGGER.debug("Device Type = %s", str(hw_type))

        if hw_type is None:
            await self._modbus.async_close()
            _LOGGER.error("Register hw_type returned None")
            raise ValueError("hw_type returned None")
        if hw_type not in CTS602_DEVICE_TYPES:
            await self._modbus.async_close()
            _LOGGER.error("HW type not supported")
            raise ValueError("HW type not supported")

        bus_version = await self.get_bus_version()

        _LOGGER.debug("Bus version = %s", str(bus_version))
        if bus_version is None:
            await self._modbus.async_close()
            _LOGGER.error("Register bus_version returned None")
            raise ValueError("bus_version returned None")
        if hw_type == 44:
            self._air_geo_type = await self.check_air_geo()

        self._device_sw_ver = await self.get_controller_software_version()
        _LOGGER.debug("Device Software = %s", self._device_sw_ver)
        if self._air_geo_type == 1:
            self._device_type = DEVICE_TYPES[hw_type] + " AIR"
        elif self._air_geo_type == 2:
            self._device_type = DEVICE_TYPES[hw_type] + " GEO"
        else:
            self._device_type = DEVICE_TYPES[hw_type]
        if (bus_version >= 10) or (self._air_geo_type != 0):
            co2_present = await self.get_co2_present()
        else:
            co2_present = False
        if self._air_geo_type == 0:
            for entity, value in ENTITY_MAP.items():
                if "min_bus_version" not in value:
                    continue
                if bus_version >= value["min_bus_version"] and (
                    hw_type in value["supported_devices"]
                    or "all" in value["supported_devices"]
                ):
                    if "excluded_bus_versions" in value:
                        if bus_version in value["excluded_bus_versions"]:
                            continue
                    if "extra_type" in value:
                        if co2_present and value["extra_type"] == "co2":
                            self._attributes[entity] = value["entity_type"]
                        else:
                            continue
                    if "max_bus_version" in value:
                        if bus_version >= value["max_bus_version"]:
                            continue
                    self._attributes[entity] = value["entity_type"]
        else:
            for entity, value in ENTITY_MAP.items():
                if "min_hps_bus_version" not in value:
                    continue
                if bus_version >= value["min_hps_bus_version"] and (
                    hw_type in value["supported_devices"]
                    or "all" in value["supported_devices"]
                ):
                    if "extra_type" in value:
                        if co2_present and value["extra_type"] == "co2":
                            self._attributes[entity] = value["entity_type"]
                        else:
                            continue
                    self._attributes[entity] = value["entity_type"]

        if "get_controller_hardware_version" in self._attributes:
            self._device_hw_ver = await self.get_controller_hardware_version()

    def get_assigned(self, platform: str):
        """Get platform assignment."""
        slots = self._attributes
        return [key for key, value in slots.items() if value == platform]

    @property
    def get_device_name(self):
        """Device name."""
        return self._device_name

    @property
    def get_device_type(self):
        """Device type."""
        return self._device_type

    @property
    def get_device_hw_version(self):
        """Device hardware version."""
        return self._device_hw_ver

    @property
    def get_device_sw_version(self):
        """Device hardware version."""
        return self._device_sw_ver

    @property
    def get_attributes(self):
        """Return device attributes."""
        return self._attributes
