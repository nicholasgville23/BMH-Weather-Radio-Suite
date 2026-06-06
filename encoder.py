import datetime
import logging

log = logging.getLogger("BMH")

def generate_same_header(org, event, location_list, duration_minutes, sender_id):
    """
    Generates a SAME header string: ZCZC-ORG-EEE-PSSCCC-PSSCCC+TTTT-JJJHHMM-LLLLLLLL-
    """
    now = datetime.datetime.utcnow()
    julian_day = now.strftime("%j")
    time_str = now.strftime("%H%M")
    
    # Format duration (TTTT)
    hours = duration_minutes // 60
    mins = duration_minutes % 60
    duration_str = f"{hours:02d}{mins:02d}"
    
    # Format locations
    locations = "-".join([f"{loc:06d}" for loc in location_list])
    
    header = f"ZCZC-{org}-{event}-{locations}+{duration_str}-{julian_day}{time_str}-{sender_id}-"
    log.debug("[SAME ENCODER] Generated Header: %s", header)
    return header

def generate_eom():
    """Generates the End of Message string."""
    return "NNNN"

if __name__ == "__main__":
    # Example usage for a Tornado Warning
    test_header = generate_same_header(
        org="WXR", 
        event="TOR", 
        location_list=[26127], # Valparaiso/Porter County
        duration_minutes=45, 
        sender_id="WNG689"
    )
    print(f"Header: {test_header}")
    print(f"EOM: {generate_eom()}")