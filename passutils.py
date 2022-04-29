import logging
import math
import os
import subprocess
import time
from datetime import datetime, timedelta

import ephem

import config
import core
from core import Recording, Satellite

logger = logging.getLogger("main.passutils")


# Schedule a pass job
def schedulePass(pass_to_add, satellite, custom_aos=0, custom_los=0):
    # Allow setting custom aos/los
    if custom_aos == 0:
        custom_aos = pass_to_add.aos
    if custom_los == 0:
        custom_los = pass_to_add.los

    # Schedule the task
    core.scheduler.add_job(
        recordPass, "date", [satellite, custom_los, pass_to_add], run_date=custom_aos
    )
    logger.info(
        f"Scheduled {satellite.name} pass at {str(custom_aos)} "
        f"with max elevation of {pass_to_add.max_elevation_deg}"
    )


# Schedule passes and resolve conflicts
def updatePass():
    passes = list()
    timenow = datetime.utcnow()

    # Lookup next passes of all satellites
    for satellite in config.satellites:
        predictor = satellite.get_predictor()
        next_pass = predictor.get_next_pass(
            config.location, max_elevation_gt=satellite.min_elevation
        )
        max_elevation = next_pass.max_elevation_deg
        priority = satellite.priority

        # Filter those coming in the next hour
        if next_pass.aos < timenow + timedelta(hours=1):
            passes.append([next_pass, satellite, max_elevation, priority])

    # Solve conflicts, a conflict being 2 satellites over horizon at the same time
    for current_pass in passes:
        current_pass_obj = current_pass[0]
        current_sat_obj = current_pass[1]
        current_max_ele = current_pass[2]
        current_priority = current_pass[3]

        keep = True
        keep_modified = False
        custom_aos = 0
        custom_los = 0
        for next_pass, satellite, max_elevation, priority in passes:
            # Skip if this is the same
            if next_pass == current_pass_obj:
                continue

            # Test if those 2 conflicts
            if (
                next_pass.aos <= current_pass_obj.los
                and not next_pass.los <= current_pass_obj.aos
            ):
                # If the priority is the same, chose the best pass
                if current_priority == priority:
                    if current_max_ele < max_elevation:
                        keep = False

                        # Schedule the pass if it doesn't overlap too much
                        overlapping_time = current_pass_obj.los - next_pass.aos
                        if overlapping_time < timedelta(minutes=config.maximum_overlap):
                            keep_modified = True
                            custom_aos = current_pass_obj.aos
                            custom_los = next_pass.aos
                else:
                    # Always prefer higher priorities
                    if current_priority < priority:
                        keep = False

                        # Schedule the pass if it doesn't overlap too much
                        overlapping_time = current_pass_obj.los - next_pass.aos
                        if overlapping_time < timedelta(minutes=config.maximum_overlap):
                            keep_modified = True
                            custom_aos = current_pass_obj.aos
                            custom_los = next_pass.aos

        # Schedule the task
        if keep:
            schedulePass(current_pass_obj, current_sat_obj)
        elif keep_modified:
            schedulePass(
                current_pass_obj,
                current_sat_obj,
                custom_aos=custom_aos,
                custom_los=custom_los,
            )


# APT Pass record function
def recordAPT(satellite, end_time):
    logger.info(f"AOS {satellite.name}...")
    date = datetime.utcnow()

    # Build filename
    filename = (
        config.output_dir
        + "/"
        + satellite.name
        + "/"
        + satellite.name
        + "_"
        + datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    )
    logger.info(
        f"Recording APT satellite {satellite.name} at {satellite.frequency}MHz to '{filename}'"
    )

    # Build command. We receive with rtl_fm and output a .wav with ffmpeg
    command = (
        f"rtl_fm -f {str(satellite.frequency)}M -s 48000 -p -6 - | "
        f"ffmpeg -hide_banner -f s16le -channels 1 -sample_rate 48k -i pipe:0 -f wav '{filename}.wav'"
    )
    subprocess.Popen([command], shell=True)

    # Wait until pass is over
    while end_time >= datetime.utcnow():
        time.sleep(1)

    # End our command
    subprocess.Popen("killall rtl_fm".split(" "))

    logger.info(f"LOS {satellite.name}...")

    # Give it some time to exit and queue the decoding
    time.sleep(10)
    return (filename, date)


# LRPT Pass record function
def recordLRPT(satellite, end_time):
    logger.info(f"AOS {satellite.name}...")
    date = datetime.utcnow()

    # Build filename
    filename = (
        config.output_dir
        + "/"
        + satellite.name
        + "/"
        + satellite.name
        + "_"
        + datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    )
    logger.info(
        f"Recording LRPT satellite {satellite.name} at {satellite.frequency}Mhz to '{filename}'"
    )

    # Build command. We receive with rtl_fm and output a raw output to feed into the demodulator
    command = f"rtl_fm -M raw -s 140000 -f {str(satellite.frequency)}M -p -6 -E dc '{filename}.raw'"
    subprocess.Popen([command], shell=True)

    # Wait until pass is over
    while end_time >= datetime.utcnow():
        time.sleep(1)

    # End our command
    subprocess.Popen("killall rtl_fm".split())

    logger.info(f"LOS {satellite.name} ...")

    # Give it some time to exit and queue the decoding
    time.sleep(10)
    return (filename, date)


# Downlink mode redirection
def recordPass(satellite, end_time, passobj):
    # Lock the radio to prevent any issues
    core.radio_lock.acquire()

    filename = str()
    date = 0

    # Record the pass!
    if satellite.downlink == "APT":
        filename, date = recordAPT(satellite, end_time)
    elif satellite.downlink == "LRPT":
        filename, date = recordLRPT(satellite, end_time)

    # Release the radio
    core.radio_lock.release()

    # Queue decoding
    core.decoding_queue.append(Recording(satellite, filename, date, passobj))


# Decode APT file
def decodeAPT(filename, satellite: Satellite, passobj):
    output_files = list()
    # sate name to use in noaa-apt command with the format "noaa_1x"
    sate_name = satellite.name.lower()
    logger.info(f"Decoding APT {sate_name} in '{filename}'")

    # get if pas is ascending (South to North)
    # TODO: move somewhere else and cleanup
    predictor = satellite.get_predictor()
    lat_at_aos = predictor.get_position(passobj.aos).position_llh[0]
    lat_after_aos = predictor.get_position(
        passobj.aos + timedelta(seconds=1)
    ).position_llh[0]
    is_ascending = lat_after_aos > lat_at_aos

    command = f"noaa-apt --rotate {'yes' if is_ascending else 'no'} -s {sate_name} '{filename}.wav' -o '{filename}.png'"

    # Run and delete the recording to save disk space
    if (
        subprocess.Popen([command], shell=True).wait() == 0
        and satellite.delete_processed_files
    ):
        os.remove(filename + ".wav")

    # Return a list of produced outputs
    output_files.append(filename + ".png")

    logger.info(f"Done decoding APT '{filename}'!")

    return output_files


# Decode LRPT file
def decodeLRPT(filename, satellite):
    output_files = list()
    logger.info(f"Demodulating LRPT '{filename}'")

    # Demodulate with meteor_demod
    if satellite.name == "METEOR-M2_2":  # Add OQPSK mode for M2 sates
        command = (
            f"meteor_demod -m oqpsk -B -s 140000 '{filename}.raw' -o '{filename}.lrpt'"
        )
    else:
        command = f"meteor_demod -B -s 140000 '{filename}.raw' -o '{filename}.lrpt'"

    if (
        subprocess.Popen([command], shell=True).wait() == 0
        and satellite.delete_processed_files
    ):
        os.remove(filename + ".raw")

    logger.info(f"Decoding LRPT '{filename}'")

    # Decode with meteor_decoder. Both IR & Visible
    command1 = f"medet '{filename}.lrpt' '{filename}-Visible' -r 65 -g 65 -b 64"
    command2 = f"medet '{filename}.lrpt' '{filename}-Infrared' -r 68 -g 68 -b 68"
    if satellite.name == "METEOR-M2_2":  # Add -diff coding for M2 sates
        command1 += " -diff"
        command2 += " -diff"
    process2 = subprocess.Popen([command2], shell=True)
    if (
        subprocess.Popen([command1], shell=True).wait() == 0
        and process2.wait() == 0
        and satellite.delete_processed_files
    ):
        try:
            os.remove(filename + ".lrpt")
        except FileNotFoundError:
            logger.error(
                f"File {filename}.lrpt not found. Might be because meteor_demod failed silently."
            )

    # Convert to png to save on space
    command1 = (
        f"ffmpeg -hide_banner -i '{filename}-Visible.bmp' '{filename}-Visible.png' "
    )
    command2 = (
        f"ffmpeg -hide_banner -i '{filename}-Infrared.bmp' '{filename}-Infrared.png' "
    )
    if (
        subprocess.Popen([command1], shell=True).wait() == 0
        and subprocess.Popen([command2], shell=True).wait() == 0
        and satellite.delete_processed_files
    ):
        try:
            os.remove(filename + "-Visible.bmp")
            os.remove(filename + "-Infrared.bmp")
        except FileNotFoundError:
            logger.error(
                f"No bitmaps found for {filename}. Symptom that medet command has failed silently"
            )

    # Correct image geometry
    command1 = f"python3 /home/pi/src/meteor_corrector/correct.py '{filename}-Visible.png' -o '{filename}-Visible.png'"
    command2 = f"python3 /home/pi/src/meteor_corrector/correct.py '{filename}-Infrared.png' -o '{filename}-Infrared.png'"

    subprocess.Popen([command1], shell=True).wait()
    subprocess.Popen([command2], shell=True).wait()

    # Return a list of produced outputs
    output_files.append(filename + "-Visible.png")
    output_files.append(filename + "-Infrared.png")

    logger.info(f"Done decoding LRPT '{filename}'!")

    return output_files


# Redirect to the right decoder function
def decodePass(filename, satellite, date, passobj):
    output_files = list()
    if satellite.downlink == "APT":
        output_files = decodeAPT(filename, satellite, passobj)
    elif satellite.downlink == "LRPT":
        output_files = decodeLRPT(filename, satellite)
    else:
        return

    # Add on the RSS feed if enabled
    if config.rss_enabled:
        import rss

        rss.addRSSPass(
            satellite, filename.replace(config.output_dir + "/", ""), date, passobj
        )

    # Process post-processing hook if enabled
    if config.post_processing_hook_enabled:
        is_daytime = pass_at_daytime(
            passobj.aos,
            config.location.latitude_deg,
            config.location.longitude_deg,
            config.location.elevation_m,
        )

        if passobj.max_elevation_deg >= config.post_processing_hook_min_elevation:
            if config.post_processing_hook_daytime_only and is_daytime:
                if config.post_processing_hook_foreach:
                    for file_out in output_files:
                        command = config.post_processing_hook_command.replace(
                            "{file}", f"'{file_out}'"
                        )
                        subprocess.Popen([command], shell=True).wait()
                else:
                    file_list = str()
                    for file_out in output_files:
                        file_list += f"'{file_out}' "
                    command = config.post_processing_hook_command.replace(
                        "{file}", file_list
                    )
                    subprocess.Popen([command], shell=True).wait()


# Process pending decodings
def processDecodeQueue():
    while True:
        time.sleep(1)
        if len(core.decoding_queue) > 0:
            decode = core.decoding_queue[0]
            decodePass(decode.filename, decode.satellite, decode.date, decode.passobj)
            core.decoding_queue.remove(decode)


def pass_at_daytime(aos, lat, lon, elev) -> bool:
    sun = ephem.Sun()
    observer = ephem.Observer()
    observer.lat, observer.lon, observer.elevation = lat, lon, elev
    observer.date = aos
    sun.compute(observer)
    # alt is in radians so convert to degrees. Use the nautical night (-12º) to get the funky shadows
    return sun.alt * 180 / math.pi > -12
