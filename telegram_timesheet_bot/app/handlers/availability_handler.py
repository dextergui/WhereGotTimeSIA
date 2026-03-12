from ..state import get, update, clear
from .. import telegram_bot, service


def start(chat_id):
    telegram_bot.send_message(chat_id, "Send person's name.")


def handle(chat_id, text):

    state = get(chat_id)

    if state["step"] == "await_name":

        update(
            chat_id,
            step="await_trips",
            current_name=text
        )

        telegram_bot.send_message(chat_id, "Send trips text.")
        return


    if state["step"] == "await_trips":

        parsed = service.parse_timesheet(text)

        state["data"]["people"].append({
            "name": state["current_name"],
            "entries": parsed["entries"]
        })

        keyboard = {
            "inline_keyboard": [[
                {"text": "Add more", "callback_data": "ADD_MORE"},
                {"text": "Start search", "callback_data": "START_SEARCH"}
            ]]
        }

        telegram_bot.send_message(
            chat_id,
            "Trips added.",
            reply_markup=keyboard
        )

        update(chat_id, step="decision")

def callback(chat_id, data):

    state = get(chat_id)

    if data == "ADD_MORE":

        update(chat_id, step="await_name")

        telegram_bot.send_message(chat_id, "Send next name.")
        return


    if data == "START_SEARCH":

        people = state["data"]["people"]

        result = service.find_common_locations(people)

        telegram_bot.send_message(chat_id, result)

        clear(chat_id)