"""
Local test script for Timings Mode feature.
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.timings_service import (
    validate_reporting_time,
    calculate_timings,
    calculate_station_timings,
    get_user_config,
    update_user_config,
    CONFIG_FILE
)

def run_tests():
    print("=== Running Timings Mode Tests ===")
    
    # 1. Validation Tests
    print("Testing validation...")
    assert validate_reporting_time("0610") == True
    assert validate_reporting_time("2359") == True
    assert validate_reporting_time("0000") == True
    assert validate_reporting_time("2400") == False
    assert validate_reporting_time("120") == False
    assert validate_reporting_time("abcd") == False
    assert validate_reporting_time("") == False
    print("  - Validation OK")

    # 2. Calculation with Defaults
    print("Testing calculation with defaults...")
    mock_chat_id = 9999999
    
    # Clean up previous test run if any
    if os.path.exists(CONFIG_FILE):
        try:
            import json
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            data.pop(str(mock_chat_id), None)
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    # Exiting Singapore default calculation
    expected_default = (
        "1900 - Bedtime 😴\n"
        "0300 - Wake up ⏰\n"
        "0440 - Leave House 🚗\n"
        "0540 - Briefing Room 🚺\n"
        "0610 - Reporting Time ✈️"
    )
    actual_default = calculate_timings("0610", mock_chat_id)
    print("Actual default timings output:\n" + actual_default)
    assert actual_default == expected_default
    print("  - Default timings calculation OK")

    # Exiting Station default calculation
    expected_stn_default = (
        "2020 - Wake up ⏰\n"
        "2220 - Leave room 🚪\n"
        "2230 - Wake Up call 📞\n"
        "2300 - Assemble 👥"
    )
    actual_stn_default = calculate_station_timings("2230", mock_chat_id)
    print("Actual default station timings output:\n" + actual_stn_default)
    assert actual_stn_default == expected_stn_default
    print("  - Default station timings calculation OK")

    # 3. Setting custom configuration
    print("Testing custom configuration updates...")
    # Change briefing room offset to 45 mins, sleep to 7 hours (420 mins)
    update_user_config(mock_chat_id, "briefing_room_offset", 45)
    update_user_config(mock_chat_id, "sleep_duration", 420)
    # Change station wake up offset to 90 mins
    update_user_config(mock_chat_id, "station_wake_up_offset", 90)
    
    # Verify custom config
    cfg = get_user_config(mock_chat_id)
    assert cfg["briefing_room_offset"] == 45
    assert cfg["sleep_duration"] == 420
    assert cfg["station_wake_up_offset"] == 90
    assert cfg["leave_house_offset"] == 60 # unchanged
    
    # Recalculate Singapore:
    # Reporting: 0610
    # Briefing: 0610 - 45m = 0525
    # Leave House: 0525 - 60m = 0425
    # Wake Up: 0425 - 100m = 0245
    # Bedtime: 0245 - 7h (420m) = 1945
    expected_custom = (
        "1945 - Bedtime 😴\n"
        "0245 - Wake up ⏰\n"
        "0425 - Leave House 🚗\n"
        "0525 - Briefing Room 🚺\n"
        "0610 - Reporting Time ✈️"
    )
    actual_custom = calculate_timings("0610", mock_chat_id)
    print("Actual custom timings output:\n" + actual_custom)
    assert actual_custom == expected_custom
    
    # Recalculate Station:
    # Wake Up Call: 2230
    # Leave Room: 2230 - 10m = 2220
    # Wake Up: 2220 - 90m = 2050
    # Assemble: 2230 + 30m = 2300
    expected_stn_custom = (
        "2050 - Wake up ⏰\n"
        "2220 - Leave room 🚪\n"
        "2230 - Wake Up call 📞\n"
        "2300 - Assemble 👥"
    )
    actual_stn_custom = calculate_station_timings("2230", mock_chat_id)
    print("Actual custom station timings output:\n" + actual_stn_custom)
    assert actual_stn_custom == expected_stn_custom
    
    print("  - Custom configuration and calculations OK")

    # 4. Clean up mock chat ID from JSON config
    if os.path.exists(CONFIG_FILE):
        try:
            import json
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            data.pop(str(mock_chat_id), None)
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    print("All timings mode tests passed successfully!")

if __name__ == "__main__":
    run_tests()
