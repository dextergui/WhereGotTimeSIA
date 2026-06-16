import json
import os
import datetime
from typing import Dict

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_timings_config.json")

DEFAULT_CONFIG = {
    # Exiting Singapore
    "briefing_room_offset": 30,  # minutes before reporting
    "leave_house_offset": 60,    # minutes before briefing
    "wake_up_offset": 100,       # minutes before leaving house
    "sleep_duration": 480,       # minutes of sleep
    # Exiting Station
    "station_assemble_offset": 30,      # minutes after wake up call
    "station_leave_room_offset": 10,     # minutes before wake up call
    "station_wake_up_offset": 120        # minutes before leave room
}

def load_configs() -> Dict[str, Dict]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_configs(configs: Dict[str, Dict]):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=4)
    except Exception:
        pass

def get_user_config(chat_id: int) -> Dict[str, int]:
    configs = load_configs()
    return configs.get(str(chat_id), DEFAULT_CONFIG.copy())

def update_user_config(chat_id: int, key: str, value: int):
    configs = load_configs()
    user_conf = configs.setdefault(str(chat_id), DEFAULT_CONFIG.copy())
    user_conf[key] = value
    save_configs(configs)

def validate_reporting_time(time_str: str) -> bool:
    """Validate format is HHMM (4 digits) and represents a valid time"""
    if not time_str or len(time_str) != 4 or not time_str.isdigit():
        return False
    try:
        hh = int(time_str[:2])
        mm = int(time_str[2:])
        datetime.time(hh, mm)
        return True
    except ValueError:
        return False

def calculate_timings(reporting_time_str: str, chat_id: int) -> str:
    """Calculate the timeline working backwards from reporting time"""
    if not validate_reporting_time(reporting_time_str):
        raise ValueError("Invalid reporting time format. Must be HHMM (e.g. 0610).")

    hh = int(reporting_time_str[:2])
    mm = int(reporting_time_str[2:])
    
    # We use a dummy date (e.g., today) to perform delta calculations
    base_date = datetime.date.today()
    reporting_dt = datetime.datetime.combine(base_date, datetime.time(hh, mm))
    
    config = get_user_config(chat_id)
    
    briefing_dt = reporting_dt - datetime.timedelta(minutes=config.get("briefing_room_offset", 30))
    leave_dt = briefing_dt - datetime.timedelta(minutes=config.get("leave_house_offset", 60))
    wake_dt = leave_dt - datetime.timedelta(minutes=config.get("wake_up_offset", 100))
    bedtime_dt = wake_dt - datetime.timedelta(minutes=config.get("sleep_duration", 480))
    
    lines = [
        f"{bedtime_dt.strftime('%H%M')} - Bedtime 😴",
        f"{wake_dt.strftime('%H%M')} - Wake up ⏰",
        f"{leave_dt.strftime('%H%M')} - Leave House 🚗",
        f"{briefing_dt.strftime('%H%M')} - Briefing Room 🚺",
        f"{reporting_dt.strftime('%H%M')} - Reporting Time ✈️"
    ]
    return "\n".join(lines)


def calculate_station_timings(wakeup_call_time_str: str, chat_id: int) -> str:
    """Calculate outstation timeline based on Wake Up Call time"""
    if not validate_reporting_time(wakeup_call_time_str):
        raise ValueError("Invalid wake up call time format. Must be HHMM (e.g. 2230).")

    hh = int(wakeup_call_time_str[:2])
    mm = int(wakeup_call_time_str[2:])
    
    base_date = datetime.date.today()
    wakeup_call_dt = datetime.datetime.combine(base_date, datetime.time(hh, mm))
    
    config = get_user_config(chat_id)
    
    leave_dt = wakeup_call_dt - datetime.timedelta(minutes=config.get("station_leave_room_offset", 10))
    wake_dt = leave_dt - datetime.timedelta(minutes=config.get("station_wake_up_offset", 120))
    assemble_dt = wakeup_call_dt + datetime.timedelta(minutes=config.get("station_assemble_offset", 30))
    
    lines = [
        f"{wake_dt.strftime('%H%M')} - Wake up ⏰",
        f"{leave_dt.strftime('%H%M')} - Leave room 🚪",
        f"{wakeup_call_dt.strftime('%H%M')} - Wake Up call 📞",
        f"{assemble_dt.strftime('%H%M')} - Assemble 👥"
    ]
    return "\n".join(lines)
