import json
import logging
from area_observations import getRegional

log = logging.getLogger("BMH")

def getRegionWeatherRoundup():
    """
    Generates the Region Weather Roundup (RWR) product.
    Similar to observations but formatted as a distinct broadcast segment.
    """
    try:
        config = json.load(open('config.json', encoding='utf-8'))
        regional_codes = config['Observations'].get('regionalObsCodes', [])
        
        if not regional_codes:
            log.warning("[RWR] No regional codes configured for Roundup.")
            return None

        log.info("[RWR] Generating Region Weather Roundup...")
        
        roundup_text = "And now, the region weather roundup. "
        
        # This relies on the existing logic in area_observations but collects it specifically
        # In a full implementation, we would extract the core logic from getRegional into a utility
        # For now, we utilize the script-based approach.
        
        # Placeholder for compiled RWR text logic
        roundup_text += "Observations from around the area. "
        
        log.debug("[RWR] Product text prepared.")
        return roundup_text

    except Exception as e:
        log.error("[RWR] Error generating Roundup: %s", e)
        return None

if __name__ == "__main__":
    print(getRegionWeatherRoundup())