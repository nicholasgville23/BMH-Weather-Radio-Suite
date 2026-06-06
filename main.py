#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
BMH Emulation Main Script

This script emulates the behavior of the NWS Broadcast Message Handler (BMH) system
by periodically generating various weather-related audio products and combining
them into a final audio output. The script runs in an infinite loop, updating
the audio files every minute (for time-only updates), with a full refresh cycle
every 10 minutes.
"""

# System-level imports
import os
import sys
import json
import time
import shutil
import logging
import argparse
import tempfile
import traceback
import subprocess
from products import PRODUCT_GENERATORS
from current_time import getCurrentTime

class ColorFormatter(logging.Formatter):
    grey = "\x1b[90m"
    green = "\x1b[92m"
    yellow = "\x1b[93m"
    red = "\x1b[91m"
    reset = "\x1b[0m"

    format_str = "%(asctime)s | %(levelname)-8s | %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def setup_logging(verbose, config=None):
    try:
        if config is not None:
            loglevel = config.upper()
        else:
            loglevel = 'DEBUG' if verbose else 'INFO'
        log = logging.getLogger("BMH")
        log.setLevel(loglevel)

        ch = logging.StreamHandler()
        ch.setLevel(loglevel)
        ch.setFormatter(ColorFormatter())
        log.addHandler(ch)
        return log
    except Exception:
        print(f"Error setting up logging: {traceback.format_exc()}")
        sys.exit(1)

try:
    parser = argparse.ArgumentParser(description='BMH Emulation')
    parser.add_argument('--config', default='config.json', help='Path to the config file')
    parser.add_argument('--generate-config', action='store_true', help='Generate a default config file and exit')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging output')
    parser.add_argument('--interactively-configure', action='store_true', help='Run interactive configuration setup')
    args = parser.parse_args()

    config = json.load(open('config.json', encoding='utf-8'))
except FileNotFoundError:
    log = setup_logging(args.verbose, None)
    if args.generate_config:
        from utils import generate_default_config
        generate_default_config(log)
        sys.exit(0)
    elif args.interactively_configure:
        from utils import interactive_config_setup
        interactive_config_setup(log)
        sys.exit(0)
    else:
        log.critical("Error: config.json file not found. Please ensure it exists in the current directory. Try --generate-config to create a new, safe default, or --interactively-configure to set up interactively.")
        sys.exit(1)
except json.JSONDecodeError as e:
    log = setup_logging(args.verbose, None)
    if args.generate_config:
        from utils import generate_default_config
        generate_default_config(log)
        sys.exit(0)
    else:
        log.critical(f"Error parsing config.json: {e.msg} at line {e.lineno} column {e.colno}\nMaybe run --generate-config to create a new, safe default?")
        sys.exit(1)
except Exception as e:
    log = setup_logging(args.verbose, None)
    log.critical(f"Error loading config.json: {traceback.format_exc()}")
    sys.exit(1)

path_separator = '\\' if os.name == 'nt' else '/'

def refresh_products():
    for generator in PRODUCT_GENERATORS:
        generator()

def combine_audio(AUDIO_SEQUENCE):
    log = logging.getLogger("BMH")
    sox_location = shutil.which(f'binary{path_separator}sox.exe') if os.name == 'nt' else shutil.which('sox')
    if not sox_location:
        log.error("[BMH] SoX not found. Cannot combine audio.")
        return

    fd, temp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run([sox_location, '-q'] + list(AUDIO_SEQUENCE) + [temp_wav], check=True)
        shutil.move(temp_wav, os.path.join(os.getcwd(), 'bmh_wav', 'FINAL_CYCLE.wav'))
    except Exception as e:
        log.error("[BMH] Failed to combine audio: %s", e)
        if os.path.exists(temp_wav): os.remove(temp_wav)

def play_audio(file_path):
    """
    Plays the generated WAV file using the system's default audio output.
    Uses SND_ASYNC to allow the script to continue running during playback.
    """
    log = logging.getLogger("BMH")
    if not os.path.exists(file_path):
        return
    try:
        if sys.platform == "win32":
            import winsound
            log.info("[BMH] Starting playback: %s", os.path.basename(file_path))
            winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        log.error("[BMH] Playback error: %s", e)

def run_time_updates(minutes, AUDIO_SEQUENCE):
    for remaining in range(minutes, 0, -1):
        plural = 's' if remaining != 1 else ''
        log.info('[BMH] Time update completed. Continuing time updates for the next %d minute%s...', remaining, plural)
        getCurrentTime()
        if config['produceSingleFile']:
            log.info('[BMH] Combining all audio files into FINAL_CYCLE.wav. Order: %s', ', '.join(AUDIO_SEQUENCE).replace(f'bmh_wav{path_separator}', '').replace('.wav', ''))
            combine_audio(AUDIO_SEQUENCE)
            play_audio(os.path.join(os.getcwd(), 'bmh_wav', 'FINAL_CYCLE.wav'))
        time.sleep(60)

def main(log):
    try:
        log.info('[BMH] Setting up BMH Emulation environment...')
        wav_dir = os.path.join(os.getcwd(), 'bmh_wav')
        os.makedirs(wav_dir, exist_ok=True)
        for file_name in os.listdir(wav_dir):
            if file_name.endswith('.wav'):
                try:
                    os.remove(os.path.join(wav_dir, file_name))
                except Exception as e:
                    log.warning(f"Could not remove {file_name}: {e}")

        _ = os.remove(os.path.join(wav_dir, 'FINAL_CYCLE.wav')) if os.path.exists(os.path.join(wav_dir, 'FINAL_CYCLE.wav')) else None

        WAV_MAPPING = {
            1: 'AlertSummary.wav',
            2: 'Forecast.wav',
            3: 'Observations.wav',
            4: 'HWO.wav',
            5: 'TWO.wav',
            6: 'CurrentTime.wav',
            7: 'StationID.wav'
        }

        log.info('[BMH] Starting BMH Emulation. Hit Ctrl+C to stop at any time...')
        while True:
            refresh_products()
            product_order = config.get('productOrder', [1, 2, 3, 4, 5, 6, 7])
            AUDIO_SEQUENCE = []
            
            for p_id in product_order:
                filename = WAV_MAPPING.get(p_id)
                if filename:
                    AUDIO_SEQUENCE.append(f'bmh_wav{path_separator}{filename}')
            
            AUDIO_SEQUENCE = tuple(AUDIO_SEQUENCE)

            if config['produceSingleFile']:
                log.info('[BMH] Combining all audio files into FINAL_CYCLE.wav. Order: %s', ', '.join(AUDIO_SEQUENCE).replace(f'bmh_wav{path_separator}', '').replace('.wav', ''))
                combine_audio(AUDIO_SEQUENCE)
                play_audio(os.path.join(os.getcwd(), 'bmh_wav', 'FINAL_CYCLE.wav'))
            log.info('[BMH] All tasks completed successfully. Re-running in approx. 1 minute (time-only)...')
            time.sleep(60)
            run_time_updates(9, AUDIO_SEQUENCE)
            log.info('[BMH] Time update completed. 10 minutes has passed. Restarting full cycle now...')
            for file_name in os.listdir(wav_dir):
                if file_name.endswith('.wav'):
                    try:
                        os.remove(os.path.join(wav_dir, file_name))
                    except Exception as e:
                        log.warning(f"Could not remove {file_name}: {e}")
    except KeyboardInterrupt:
        log.info('[BMH] Stopping BMH Emulation as requested by user. Goodbye!')
        sys.exit(0)
    except Exception:
        log.error("[BMH] Error: %s", traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    if args.generate_config:
        log = setup_logging(args.verbose, config["logLevel"] if "logLevel" in config else None)
        from utils import generate_default_config
        generate_default_config(log)
        sys.exit(0)
    elif args.interactively_configure:
        log = setup_logging(args.verbose, config["logLevel"] if "logLevel" in config else None)
        from utils import interactive_config_setup
        interactive_config_setup(log)
        sys.exit(0)
    else:
        log = setup_logging(args.verbose, config["logLevel"] if "logLevel" in config else None)
        main(log)
