from .. import telegram_bot
from ..state import update, clear, get
from app.services.timings_service import (
    get_user_config,
    update_user_config,
    validate_reporting_time,
    calculate_timings,
    calculate_station_timings
)

FRIENDLY_NAMES = {
    # Singapore settings
    "briefing_room_offset": "Briefing Room offset (in minutes)",
    "leave_house_offset": "Leave House offset (in minutes)",
    "wake_up_offset": "Wake Up offset (in minutes)",
    "sleep_duration": "Sleep duration (in minutes)",
    # Station settings
    "station_assemble_offset": "Assemble offset (in minutes after Wake Up Call)",
    "station_leave_room_offset": "Leave room offset (in minutes before Wake Up Call)",
    "station_wake_up_offset": "Wake up offset (in minutes before Leave Room)"
}

def start(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "Calculate Singapore Timings", "callback_data": "TIMINGS_CALC_SIN"}],
            [{"text": "Calculate Station Timings", "callback_data": "TIMINGS_CALC_STN"}],
            [{"text": "Configure Settings", "callback_data": "TIMINGS_CONFIG_MENU"}]
        ]
    }
    telegram_bot.send_message(
        chat_id,
        "🤖 Timings Mode\nSelect an option below:",
        reply_markup=keyboard
    )

def handle(chat_id, text):
    state = get(chat_id)
    if not state:
        return

    step = state.get("step")

    if step == "await_time_sin":
        if not validate_reporting_time(text):
            telegram_bot.send_message(
                chat_id,
                "❌ Invalid format. Please enter reporting time in HHMM format (e.g. 0610)."
            )
            return
        
        try:
            result = calculate_timings(text, chat_id)
            telegram_bot.send_message(
                chat_id,
                f"⏰ Singapore Timings:\n\n{result}"
            )
            clear(chat_id)
        except Exception as e:
            telegram_bot.send_message(
                chat_id,
                f"❌ Error calculating timings: {str(e)}"
            )
            clear(chat_id)

    elif step == "await_time_stn":
        if not validate_reporting_time(text):
            telegram_bot.send_message(
                chat_id,
                "❌ Invalid format. Please enter Wake Up Call time in HHMM format (e.g. 2230)."
            )
            return
        
        try:
            result = calculate_station_timings(text, chat_id)
            telegram_bot.send_message(
                chat_id,
                f"⏰ Station Timings:\n\n{result}"
            )
            clear(chat_id)
        except Exception as e:
            telegram_bot.send_message(
                chat_id,
                f"❌ Error calculating timings: {str(e)}"
            )
            clear(chat_id)

    elif step == "await_config_value":
        config_key = state.get("config_key")
        if not config_key:
            clear(chat_id)
            return
            
        try:
            val = int(text.strip())
            if val <= 0:
                raise ValueError()
        except ValueError:
            friendly_name = FRIENDLY_NAMES.get(config_key, config_key)
            telegram_bot.send_message(
                chat_id,
                f"❌ Invalid input. Please enter a positive number of minutes for {friendly_name}."
            )
            return

        update_user_config(chat_id, config_key, val)
        telegram_bot.send_message(
            chat_id,
            f"✅ {FRIENDLY_NAMES.get(config_key, config_key)} updated to {val} minutes."
        )
        
        # Go back to corresponding config menu
        if config_key.startswith("station_"):
            show_config_station_menu(chat_id)
        else:
            show_config_singapore_menu(chat_id)

def callback(chat_id, data):
    if data == "TIMINGS_CALC_SIN":
        update(chat_id, step="await_time_sin")
        telegram_bot.send_message(
            chat_id,
            "🤖 Singapore Timings\n=> Please enter reporting time (format: HHMM, e.g. 0610):"
        )
    elif data == "TIMINGS_CALC_STN":
        update(chat_id, step="await_time_stn")
        telegram_bot.send_message(
            chat_id,
            "🤖 Station Timings\n=> Please enter Wake Up Call time (format: HHMM, e.g. 2230):"
        )
    elif data == "TIMINGS_CONFIG_MENU":
        show_config_main_menu(chat_id)
    elif data == "TIMINGS_CONFIG_SIN":
        show_config_singapore_menu(chat_id)
    elif data == "TIMINGS_CONFIG_STN":
        show_config_station_menu(chat_id)
    elif data.startswith("TIMINGS_SET_"):
        key = data[len("TIMINGS_SET_"):]
        friendly_name = FRIENDLY_NAMES.get(key, key)
        config = get_user_config(chat_id)
        current_val = config.get(key, 0)
        
        update(chat_id, step="await_config_value", config_key=key)
        telegram_bot.send_message(
            chat_id,
            f"✍️ Enter new value in minutes for {friendly_name} (current: {current_val} mins):"
        )
    elif data == "TIMINGS_MENU":
        update(chat_id, step="menu")
        start(chat_id)

def show_config_main_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "Exiting Singapore Settings", "callback_data": "TIMINGS_CONFIG_SIN"}],
            [{"text": "Exiting Station Settings", "callback_data": "TIMINGS_CONFIG_STN"}],
            [{"text": "« Back to Menu", "callback_data": "TIMINGS_MENU"}]
        ]
    }
    telegram_bot.send_message(
        chat_id,
        "⚙️ Select which timings settings to configure:",
        reply_markup=keyboard
    )

def show_config_singapore_menu(chat_id):
    config = get_user_config(chat_id)
    briefing = config.get("briefing_room_offset", 30)
    leave = config.get("leave_house_offset", 60)
    wake = config.get("wake_up_offset", 100)
    sleep = config.get("sleep_duration", 480)
    
    config_text = (
        "⚙️ Singapore Timings Settings:\n\n"
        f"1. Briefing Room: {briefing} mins before reporting\n"
        f"2. Leave House: {leave} mins before briefing\n"
        f"3. Wake Up: {wake} mins before leaving house\n"
        f"4. Sleep Duration: {sleep} mins ({round(sleep/60, 1)} hours)\n\n"
        "Select a setting to modify:"
    )
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "1. Briefing Room Offset", "callback_data": "TIMINGS_SET_briefing_room_offset"}],
            [{"text": "2. Leave House Offset", "callback_data": "TIMINGS_SET_leave_house_offset"}],
            [{"text": "3. Wake Up Offset", "callback_data": "TIMINGS_SET_wake_up_offset"}],
            [{"text": "4. Sleep Duration", "callback_data": "TIMINGS_SET_sleep_duration"}],
            [{"text": "« Back to Config Menu", "callback_data": "TIMINGS_CONFIG_MENU"}]
        ]
    }
    
    update(chat_id, step="menu")
    telegram_bot.send_message(chat_id, config_text, reply_markup=keyboard)

def show_config_station_menu(chat_id):
    config = get_user_config(chat_id)
    assemble = config.get("station_assemble_offset", 30)
    leave = config.get("station_leave_room_offset", 10)
    wake = config.get("station_wake_up_offset", 120)
    
    config_text = (
        "⚙️ Station Timings Settings:\n\n"
        f"1. Assemble: {assemble} mins after Wake Up Call\n"
        f"2. Leave Room: {leave} mins before Wake Up Call\n"
        f"3. Wake Up: {wake} mins before Leave Room\n\n"
        "Select a setting to modify:"
    )
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "1. Assemble Offset", "callback_data": "TIMINGS_SET_station_assemble_offset"}],
            [{"text": "2. Leave Room Offset", "callback_data": "TIMINGS_SET_station_leave_room_offset"}],
            [{"text": "3. Wake Up Offset", "callback_data": "TIMINGS_SET_station_wake_up_offset"}],
            [{"text": "« Back to Config Menu", "callback_data": "TIMINGS_CONFIG_MENU"}]
        ]
    }
    
    update(chat_id, step="menu")
    telegram_bot.send_message(chat_id, config_text, reply_markup=keyboard)
