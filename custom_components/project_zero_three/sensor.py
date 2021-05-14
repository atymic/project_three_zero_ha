"""Sensor platform to display the current fuel prices at a NSW fuel station."""
import datetime
import logging
from typing import Optional

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

ATTR_LATITUDE = "Latitude"
ATTR_LONGITUDE = "Longitude"


CONF_UPDATE_FREQUENCY = 'update_frequency'
CONF_UPDATE_FREQUENCY_DEFAULT = 5

CONF_FUEL_TYPES = "fuel_types"
CONF_ALLOWED_FUEL_TYPES = [
    "E10",
    "U91",
    "U95",
    "U98",
    "Diesel",
    "LPG",
]
CONF_DEFAULT_FUEL_TYPES = ["E10", "U91", "U95", "U98"]

ATTRIBUTION = "Data provided by Project Zero Three"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_UPDATE_FREQUENCY, default=CONF_UPDATE_FREQUENCY_DEFAULT): cv.positive_int,
        vol.Optional(CONF_FUEL_TYPES, default=CONF_ALLOWED_FUEL_TYPES): vol.All(
            cv.ensure_list, [vol.In(CONF_ALLOWED_FUEL_TYPES)]
        ),
    }
)

NOTIFICATION_ID = "project_zero_three_notification"
NOTIFICATION_TITLE = "Project Three Zero Setup"

# TODO figure out to how to do this dynamically
MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(minutes=5)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the NSW Fuel Station sensor."""

    update_frequency = config[CONF_UPDATE_FREQUENCY]
    fuel_types = config[CONF_FUEL_TYPES]

    data = FuelPriceData()
    data.update()

    if data.error is not None:
        message = "Error: {}. Check the logs for additional information.".format(
            data.error
        )

        hass.components.persistent_notification.create(
            message, title=NOTIFICATION_TITLE, notification_id=NOTIFICATION_ID
        )
        return

    available_fuel_types = data.get_available_fuel_types()

    add_entities(
        [
            StationPriceSensor(data, fuel_type)
            for fuel_type in fuel_types
            if fuel_type in available_fuel_types
        ]
    )


class FuelPriceData:
    """An object to store and fetch the latest data for a given station."""

    def __init__(self) -> None:
        """Initialize the sensor."""
        self._data = None
        self._reference_data = None
        self.error = None
        self._station_name = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Update the internal data using the API client."""
        try:
            res = requests.get(
                "https://projectzerothree.info/api.php?format=json",
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36 (KHTML, '
                                       'like Gecko) Chrome/80.0.3987.0 Safari/537.36 Edg/80.0.360.0'}
            )

            self._data = res.json()['regions'][0]['prices']
        except requests.RequestException as exc:
            self.error = str(exc)
            _LOGGER.error("Failed to fetch project zero three price data. %s", exc)

    def for_fuel_type(self, fuel_type: str):
        """Return the price of the given fuel type."""
        if self._data is None:
            return None
        return next(
            (price for price in self._data if price['type'] == fuel_type), None
        )

    def get_available_fuel_types(self):
        """Return the available fuel types for the station."""
        return [price['type'] for price in self._data]


class StationPriceSensor(Entity):

    """Implementation of a sensor that reports the fuel price for a station."""

    def __init__(self, data: FuelPriceData, fuel_type: str):
        """Initialize the sensor."""
        self._data = data
        self._fuel_type = fuel_type

    def get_price_data(self) -> Optional[dict]:
        """Return the state of the sensor."""
        price_info = self._data.for_fuel_type(self._fuel_type)
        if price_info:
            return price_info

        return None

    @property
    def unique_id(self) -> Optional[str]:
        """Return the name of the sensor."""
        data = self.get_price_data()
        return f"project_zero_three_{data['type']}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        data = self.get_price_data()

        if not self.registry_entry:
            return self.unique_id

        return f"{data['type']} @ {data['suburb']} {data['postcode']} ({data['state']})"

    @property
    def state(self) -> Optional[float]:
        """Return the state of the sensor."""
        data = self.get_price_data()
        if data:
            return data['price']

        return None

    @property
    def device_state_attributes(self) -> dict:
        """Return the state attributes of the device."""
        data = self.get_price_data()

        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            ATTR_LATITUDE: data['lat'] or None,
            ATTR_LONGITUDE: data['lng'] or None
        }

    @property
    def unit_of_measurement(self) -> str:
        """Return the units of measurement."""
        return "¢/L"

    def update(self):
        """Update current conditions."""
        self._data.update()
