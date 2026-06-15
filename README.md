# Telegram Timesheet OCR & Availability Bot

This is a Python FastAPI service designed to run as a Telegram Bot webhook. It parses Singapore Airlines (SIA) crew timesheets from uploaded images, extracts duty details, posts them to Google Sheets and Google Calendar, and helps find common availability among crew members.

---

## 📂 Repository Structure

The project has been reorganized into the following folder structure:

```text
├── app/                        # Main application source code
│   ├── handlers/               # Command-specific message handlers
│   │   ├── availability_handler.py  # Logic for finding common crew availability (/availability)
│   │   └── parse_handler.py         # Logic for processing/confirming timesheets (/extract)
│   ├── calendar.py             # Google Calendar integration (event creation)
│   ├── config.py               # Environment configuration and credentials decoding
│   ├── main.py                 # FastAPI application and webhook entrypoint
│   ├── models.py               # Data structures (e.g., FlightRow dataclass)
│   ├── ocr.py                  # Google Cloud Vision OCR integration
│   ├── router.py               # Main router for incoming Telegram messages & callbacks
│   ├── service.py              # Core timesheet parsing and location comparison logic
│   ├── sheets.py               # Google Sheets API helper (gspread)
│   ├── state.py                # In-memory session state management
│   └── telegram_bot.py         # Telegram Bot API requests helper
│
├── scripts/                    # Utility and testing scripts
│   ├── calendar_local_test.py  # Local helper to test calendar event creation
│   ├── local_test_update.py    # Simulates an incoming webhook update for local testing
│   ├── process_local_file.py   # Processes a local image/mock text to check parsing and sheets append
│   ├── run_tests.py            # Local snapshot test runner
│   ├── set_webhook.py          # Sets the bot's Telegram webhook URL
│   └── test_availability_local.py # Local availability search check
│
├── tests/                      # Testing assets and expected output snapshots
│   └── snapshots/              # Snapshot expectations for parser outputs, replies, and rows
│
├── Dockerfile                  # Docker image build configuration
├── Procfile                    # Render/Heroku process layout for production
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation (this file)
```

---

## 🚀 Key Features

1. **Timesheet OCR & Parsing (`/extract`)**
   - Upload an image (photo or document) of your crew timesheet.
   - The bot runs OCR via **Google Cloud Vision** and parses the text into individual duties (Flight, Standby `SS`/`STBY`, Layover `LO`, and Off-Duty `OFFD`/`ATDO`/`AALV`).
   - Responds with a clean, formatted text summary of your parsed schedule.

2. **Google Sheets Sync**
   - Authorized users can automatically append parsed flight duties and layovers to a designated Google Sheet.

3. **Google Calendar Sync**
   - Creates Google Calendar events for standbys, layovers, and flight duties directly onto the user's calendar.

4. **Common Crew Availability Finder (`/availability`)**
   - Interactive flow to collect timesheets from multiple crew members and find dates/locations where their schedules overlap (e.g., matching layover locations or shared off-days).

5. **Access Control**
   - Restricts bot command usage and data writing capabilities using telegram chat ID whitelisting (`ALLOWED_IDS` and `TRUSTED_IDS`).

---

## ⚙️ Environment Variables

The application requires the following environment variables to run:

| Variable | Required? | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token for your Telegram bot. |
| `ALLOWED_IDS` | Yes | Comma-separated list of Telegram chat IDs authorized to chat with the bot. |
| `TRUSTED_IDS` | Yes | Comma-separated list of Telegram chat IDs authorized to perform write actions (Sheets/Calendar). |
| `GOOGLE_CREDS_B64` | Yes | Base64-encoded Google service account JSON credential (or raw JSON string) for Sheets, Calendar, and Cloud Vision APIs. |
| `SHEET_ID` | Yes | Target Google Sheet ID where rows will be appended. |
| `SHEET_NAME` | No | Worksheet title inside the Google Sheet (defaults to `Sheet1`). |
| `CALENDAR_ID` | No | Google Calendar ID to push events to (defaults to `primary`). |
| `WEBHOOK_PATH` | No | Path segment the webhook will listen on (defaults to `webhook`). |

---

## 🛠️ Local Development & Testing

### 1. Setup the Environment
Activate your Conda environment and install dependencies:
```bash
conda activate WhereGotTimeSIA
pip install -r requirements.txt
```
> **Note**: This application uses `@dataclass(slots=True)` which requires **Python 3.10+**.

### 2. Run the Development Server
Start FastAPI locally using `uvicorn`:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Run the Snapshot Test Suite
Run the automated parsing, reply, and sheet-row regression snapshot tests:
```bash
python scripts/run_tests.py
```

### 4. Process Local Files (CLI testing)
You can test the OCR and parsing pipeline on local images without launching the web server:
```bash
python scripts/process_local_file.py tests/mar26.jpg --chat 123456
```
To test appends to Google Sheets locally (using your local `.env` variables):
```bash
python scripts/process_local_file.py tests/mar26.jpg --chat 123456 --append
```

### 5. Setup / Set Webhook URL
To register your webhook URL with Telegram:
```bash
python scripts/set_webhook.py https://<your-service-domain>.com
```

---

## ☁️ Production Deployment (e.g., Render)

1. Create a new **Web Service** on Render.
2. Select your repository and set the environment variables listed in the configuration section.
3. Configure the **Start Command** as defined in the `Procfile`:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Once deployed, register the webhook with Telegram using:
   ```bash
   python scripts/set_webhook.py https://<your-render-app>.onrender.com
   ```
