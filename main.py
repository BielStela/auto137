import logging
import os
import time
from pathlib import Path
from threading import Thread

import config
import core
import passutils


def main():
    # Congifure logger
    logger = logging.getLogger('main')
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler('auto137.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s : %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Parse config, fetch some data
    config.loadConfig("config.yaml")
    logger.info('Configuration loaded/')
    core.updateTLEs()

    # Create images folders
    for satellite in config.satellites:
        if not Path(config.output_dir + "/" + satellite.name).is_dir():
            os.makedirs(config.output_dir + "/" + satellite.name)
            logger.info('Data directories structure created.')

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
        import rss
        rss.startServer()
    
    # Schedule passes
    passutils.updatePass()
    
    # Wait forever
    while True:
        time.sleep(10)


if __name__ == '__main__':
    print("+---------------------------------------+")
    print("|               Auto137                 |")
    print("+---------------------------------------+")

    main()

