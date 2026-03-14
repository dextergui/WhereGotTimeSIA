from ..state import get, update, clear
from .. import telegram_bot, service


def start(chat_id):
    telegram_bot.send_message(chat_id, """
                              📅 Availability Mode
                              => Send person's name.
                              """)


def handle(chat_id, text):

    state = get(chat_id)

    if state["step"] == "await_name":

        update(
            chat_id,
            step="await_trips",
            current_name=text
        )

        telegram_bot.send_message(chat_id, """
                                  📅 Availability Mode
                                  => Send trips text extracted from /extract.
                                  """)
        return


    if state["step"] == "await_trips":

        expected_month = state["data"].get("month")
        expected_year = state["data"].get("year")

        ok, result = service.validate_extracted_block(
            text,
            expected_month,
            expected_year
        )

        if not ok:
            telegram_bot.send_message(chat_id, f"""
                                      📅 Availability Mode
                                      => {result}
                                      """)
            return

        # first user defines month/year
        if not expected_month:
            state["data"]["month"] = result["month"]
            state["data"]["year"] = result["year"]

        state["data"]["people"].append({
            "name": state["current_name"],
            "trips": result["trips"]
        })

        keyboard = {
            "inline_keyboard": [[
                {"text": "Add more", "callback_data": "ADD_MORE"},
                {"text": "Start search", "callback_data": "START_SEARCH"}
            ]]
        }

        telegram_bot.send_message(
            chat_id,
            f"""
            📅 Availability Mode
            ✅ Trips added for {state['current_name']}
            """,
            reply_markup=keyboard
        )

        update(chat_id, step="decision")

def callback(chat_id, data):

    state = get(chat_id)

    if data == "ADD_MORE":

        update(chat_id, step="await_name")

        telegram_bot.send_message(chat_id, """
                                  📅 Availability Mode
                                  => Send next name.
                                  """)
        return


    if data == "START_SEARCH":

        people = state["data"]["people"]
        month = state["data"]["month"]
        year = state["data"]["year"]

        result = service.find_common_locations(
            people,
            month,
            year
        )

        telegram_bot.send_message(chat_id, result)

        clear(chat_id)