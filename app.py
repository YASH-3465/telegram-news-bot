import streamlit as st
import requests
import datetime
import threading
import schedule
import time
import logging

import streamlit as st

# Read secrets exactly as named in Streamlit Cloud Secrets
NEWS_API_KEY = st.secrets.get("news_api_key", "")
TELEGRAM_TOKEN = st.secrets.get("telegram_token", "")
TELEGRAM_CHAT_ID = st.secrets.get("telegram_chat_id", "")

missing = []
if not NEWS_API_KEY:
    missing.append("news_api_key")
if not TELEGRAM_TOKEN:
    missing.append("telegram_token")
if not TELEGRAM_CHAT_ID:
    missing.append("telegram_chat_id")

if missing:
    st.error(f"Missing secret(s): {', '.join(missing)}. Please add them in Streamlit Secrets.")
    st.stop()

# -------- Logging --------
LOG_FILE = "telegram_news_bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# -------- News API --------
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"

NEWS_SOURCES_MAP = {
    "timesofindia": "the-times-of-india",
    "ndtv": "ndtv",
    "indianexpress": "the-indian-express",
    "bbc-news": "bbc-news",
    "cnn": "cnn",
    "reuters": "reuters"
}

def get_news(api_key, sources, max_total=5):
    headlines = []
    try:
        for src in sources:
            source_api_name = NEWS_SOURCES_MAP.get(src)
            if not source_api_name:
                continue
            params = {
                "apiKey": api_key,
                "sources": source_api_name,
                "pageSize": max_total,
                "language": "en",
            }
            response = requests.get(NEWS_API_URL, params=params, timeout=10)
            data = response.json()
            if data.get("status") == "ok":
                articles = data.get("articles", [])
                for art in articles:
                    title = art.get("title")
                    if title and title not in headlines:
                        headlines.append(title)
                        if len(headlines) >= max_total:
                            break
            if len(headlines) >= max_total:
                break
    except Exception as e:
        logging.error(f"News API error: {e}")
    if not headlines:
        headlines.append("No news headlines found.")
    return headlines[:max_total]

# -------- Telegram send --------
def send_telegram_message(token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            logging.info("Telegram message sent successfully")
            return True
        else:
            logging.error(f"Telegram send failed: {r.status_code} {r.text}")
            return False
    except Exception as e:
        logging.error(f"Telegram send error: {e}")
        return False

# -------- Background job --------
def background_job(token, chat_id, api_key, sources):
    logging.info("Scheduler triggered")
    try:
        headlines = get_news(api_key, sources, max_total=5)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        headline_text = f"*📰 AI News Headlines ({date_str}) 📰*\n\n"
        for i, hl in enumerate(headlines, start=1):
            headline_text += f"{i}. {hl}\n\n"
        sent = send_telegram_message(token, chat_id, headline_text)
        if sent:
            logging.info("Background send succeeded")
        else:
            logging.error("Background send failed")
    except Exception as e:
        logging.error(f"Background job error: {e}")

# -------- Scheduler thread --------
def scheduler_loop():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Scheduler loop error: {e}")
        time.sleep(1)

if "sched_thread_started" not in st.session_state:
    st.session_state.sched_thread_started = True
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    logging.info("Scheduler thread started")

# -------- Streamlit UI --------
st.title("📰 Telegram AI News Bot")

# Read secrets (set these in Streamlit Cloud Secrets)
NEWS_API_KEY = st.secrets.get("news_api_key", "")
TELEGRAM_TOKEN = st.secrets.get("telegram_token", "")
TELEGRAM_CHAT_ID = st.secrets.get("telegram_chat_id", "")

st.write("Note: Your API keys and chat ID are read from Streamlit Secrets.")

sources = st.multiselect(
    "Select News Sources",
    options=list(NEWS_SOURCES_MAP.keys()),
    default=list(NEWS_SOURCES_MAP.keys())
)

send_time = st.time_input("Daily send time", value=datetime.time(8,0))
activate = st.checkbox("Activate daily sending")

if st.button("Save Settings & Schedule"):
    if not NEWS_API_KEY:
        st.error("Missing News API key in Streamlit Secrets.")
    elif not TELEGRAM_TOKEN:
        st.error("Missing Telegram bot token in Streamlit Secrets.")
    elif not TELEGRAM_CHAT_ID or not TELEGRAM_CHAT_ID.strip().isdigit():
        st.error("Missing or invalid Telegram chat ID in Streamlit Secrets.")
    elif not sources:
        st.error("Select at least one news source.")
    else:
        schedule.clear()
        if activate:
            schedule.every().day.at(send_time.strftime("%H:%M")).do(
                background_job,
                token=TELEGRAM_TOKEN,
                chat_id=TELEGRAM_CHAT_ID,
                api_key=NEWS_API_KEY,
                sources=sources
            )
            st.success(f"Scheduled daily news at {send_time.strftime('%H:%M')}")
        else:
            st.info("Scheduling deactivated.")

# Manual send now
if st.button("Send Now (Test)"):
    if not NEWS_API_KEY or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.error("Ensure all secrets are set.")
    elif not sources:
        st.error("Select at least one news source.")
    else:
        headlines = get_news(NEWS_API_KEY, sources, max_total=5)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        headline_text = f"*📰 AI News Headlines (Test) ({date_str}) 📰*\n\n"
        for i, hl in enumerate(headlines, start=1):
            headline_text += f"{i}. {hl}\n\n"
        sent = send_telegram_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, headline_text)
        if sent:
            st.success("Test message sent! Check your Telegram.")
        else:
            st.error("Failed to send test message. Check logs.")

st.markdown("---")
st.write("### Logs (latest 50 lines):")
try:
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        logs = f.readlines()[-50:]
        st.text("".join(logs))
except Exception as e:
    st.info("No logs yet or unable to read logs.")

st.markdown("---")
st.write("""
### How to use:
- Put your API keys and chat ID in Streamlit Secrets (`news_api_key`, `telegram_token`, `telegram_chat_id`).
- Select news sources and time, activate scheduling.
- Keep this app running on Streamlit Cloud.
- The bot will send daily news headlines automatically.
- Use "Send Now (Test)" to test immediate sending.
""")
