from .. import telegram_bot
from ..state import update, clear, get
from app.services.timings_service import (
    get_user_config,
    update_user_config,
    validate_reporting_time,
    calculate_timings
)

FRIENDLY_NAMES = {
    "briefing_room_offset": "Briefing Room offset (in minutes)",
    "leave_house_offset": "Leave House offset (in minutes)",
    "wake_up_offset": "Wake Up offset (in minutes)",
    "sleep_duration": "Sleep duration (in minutes)"
}

def start(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "Calculate Timings", "callback_data": "TIMINGS_CALC"}],
            [{"text": "Configure Steps", "callback_data": "TIMINGS_CONFIG"}]
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

    if step == "await_time":
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
                f"⏰ Calculated Timings:\n\n{result}"
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
        
        # Go back to config menu
        show_config_menu(chat_id)

def callback(chat_id, data):
    if data == "TIMINGS_CALC":
        update(chat_id, step="await_time")
        telegram_bot.send_message(
            chat_id,
            "🤖 Timings Mode\n=> Please enter your reporting time (format: HHMM, e.g. 0610):"
        )
    elif data == "TIMINGS_CONFIG":
        show_config_menu(chat_id)
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

def show_config_menu(chat_id):
    config = get_user_config(chat_id)
    briefing = config.get("briefing_room_offset", 30)
    leave = config.get("leave_house_offset", 60)
    wake = config.get("wake_up_offset", 100)
    sleep = config.get("sleep_duration", 480)
    
    config_text = (
        "⚙️ Current Timings Settings:\n\n"
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
            [{"text": "« Back to Menu", "callback_data": "TIMINGS_MENU"}]
        ]
    }
    
    update(chat_id, step="menu")
    telegram_bot.send_message(chat_id, config_text, reply_markup=keyboard)
