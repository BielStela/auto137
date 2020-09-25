import config
import core

import logging
import time
import passutils
import os
import rss
from datetime import datetime, timedelta
from threading import Thread
from pathlib import Path

# Gets or creates a logger
logger = logging.getLogger(__name__)  
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('auto137.log')
formatter    = logging.Formatter('%(asctime)s : %(levelname)s : %(name)s : %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

print("-----------------------------------------")
print("            Starting Auto137             ")
print("-----------------------------------------")
print("\n")

# Parse config, fetch some data
config.loadConfig("config.yaml")
logger.info('Configuration loaded.')
core.updateTLEs()

# Create images folders
for satellite in config.satellites:
    if not Path(config.output_dir + "/" + satellite.name).is_dir():
        os.makedirs(config.output_dir + "/" + satellite.name)

# Init sheduler and start repeating tasks
core.initScheduler()
core.scheduler.add_job(
    core.updateTLEs, "interval", id="tle_refresh", hours=config.tle_update_interval
)
core.scheduler.add_job(passutils.updatePass, "interval", id="passes_refresh", hours=1)
logger.info("Scheduler started!")

# Start decoding thread
decodingThread = Thread(target=passutils.processDecodeQueue)
decodingThread.start()
logger.info("Decoding thread started!")

# Start RSS Server if enabled
if config.rss_enabled:
    rss.startServer()

# Schedule passes
passutils.updatePass()

# Wait forever
while True:
    time.sleep(10)
