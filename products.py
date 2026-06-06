# Product modules, add new ones here as needed.
from Forecast import getForecast
from alert_summary import getAlertSummary
from hazardous_weather_outlook import getHazardousWeatherOutlook
from tropical_weather_outlook import getTropicalWeatherOutlook
from current_time import getCurrentTime
from area_observations import getObservations
from station_id import getStationID

PRODUCT_GENERATORS = (
    getAlertSummary,
    getForecast,
    getObservations,
    getHazardousWeatherOutlook,
    getTropicalWeatherOutlook,
    getCurrentTime,
    getStationID,
)
