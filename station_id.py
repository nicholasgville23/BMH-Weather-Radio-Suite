import sys
import json
import logging
import traceback
from utils import produce_wav_file

log = logging.getLogger("BMH")

def getStationID():
    try:
        config = json.load(open('config.json', encoding='utf-8'))
        phonemeDict = json.load(open('phonemeDB.json', encoding='utf-8'))
        replaceDict = phonemeDict['replace']
        phonemeDict = phonemeDict['phonemes']
        speed = config['ttsSpeed']
        pause = config['endPause']

        # Station Identification for WNG689 in Valparaiso, Indiana
        # Frequency: 162.450 MHz
        station_text = "This is NOAA Weather Radio station W N G 6 8 9, in Valparaiso, Indiana. Broadcasting on a frequency of 162.450 megahertz, from a transmitter near Valparaiso. This station serves residents of northwest Indiana and northeast Illinois."

        # Apply phonemes
        for phoneme in phonemeDict:
            log.debug('[STATIONID PHONEMES] Replacing %s with %s', phoneme, phonemeDict[phoneme])
            station_text = str(station_text).replace(phoneme, f'<vtml_phoneme alphabet="x-cmu" ph="{phonemeDict[phoneme]}"></vtml_phoneme>')

        # Apply replacements
        for word in replaceDict:
            log.debug('[STATIONID PHONEMES] Replacing %s with %s', word, replaceDict[word])
            if '*PAUSE' in replaceDict[word]:
                pauseTime = replaceDict[word].split('*')[1].split('-')[1]
                word_to_find = word.replace(f'*PAUSE-{pauseTime}*', f'<vtml_pause time="{pauseTime}"/>')
                station_text = str(station_text).replace(word_to_find, replaceDict[word])
            else:
                station_text = str(station_text).replace(word, replaceDict[word])

        final_text = f'<vtml_volume value="200"> <vtml_speed value="{speed}"> ' + station_text + f' <vtml_pause time="{pause}"/> </vtml_volume> </vtml_speed>'
        final_text = final_text.replace('\n', ' ').replace('\r', ' ')

        log.debug('[STATIONID] Final Text: %s', final_text)
        produce_wav_file(final_text, 'StationID.wav')

    except Exception:
        log.error('[STATIONID] %s', traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    print('[STATIONID] This is one of the BMH modules, not a standalone program. Please run main.py to execute the full BMH program.')