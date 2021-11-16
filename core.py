from satellite_tle import fetch_tle
from orbit_predictor.sources import get_predictor_from_tle_lines
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import utc
from threading import Lock
import logging

logger = logging.getLogger('main.core')

import config

# Main scheduler
scheduler = BackgroundScheduler()

# Decoding queue
decoding_queue = list()

# Radio mutex
radio_lock = Lock()

# Init scheduler
def initScheduler():
    scheduler.configure(timezone=utc)
    scheduler.start()


# Satellite class
class Satellite:
    def __init__(
        self,
        name,
        norad,
        priority,
        min_elevation,
        frequency,
        downlink,
        delete_processed_files,
    ):
        self.name = name.strip().replace(" ", "_")
        self.verbose_name = name
        self.norad = norad
        self.priority = priority
        self.min_elevation = min_elevation
        self.frequency = frequency
        self.downlink = downlink
        self.delete_processed_files = delete_processed_files

    def fetch_tle(self):
        logger.info(f'Updating TLE for {self.verbose_name}...')
        try:
            tle = fetch_tle.fetch_tle_from_celestrak(self.norad)
            name, line1, line2 = tle
            self.tle_1 = line1
            self.tle_2 = line2
        except ConnectionError as ex:
            logger.error(f"Failed to fetch the TLE for {self.name} with exception {ex}")

    def get_predictor(self):
        self.predictor = get_predictor_from_tle_lines((self.tle_1, self.tle_2))
        return self.predictor


# Recording class
class Recording:
    def __init__(self, satellite, filename, date, passobj):
        self.satellite = satellite
        self.filename = filename
        self.date = date
        self.passobj = passobj


# Update TLE
def updateTLEs():
    for satellite in config.satellites:
        satellite.fetch_tle()
    logger.info('TLEs updated!')
