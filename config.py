import os

# Telegram API Credentials
API_ID = int(os.environ.get("API_ID", "39601298"))
API_HASH = os.environ.get("API_HASH", "aa2e389a709620d70b3fe6f54965bc66")

# Bot Token from BotFather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8748194201:AAHfRjJsQVE13FxrIgA09zKbe4iyUxE3YkM")

# MongoDB Connection String
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://infovedanthin_db_user:F1fMSlMMNBj9tMnl@cluster0.azzars4.mongodb.net/?appName=Cluster0")

# Lite-Short API Key & Base URL
SHORTENER_API = os.environ.get("SHORTENER_API", "9dae21b3b0398712b695e03098c6989b33edc5a9")
SHORTENER_URL = "https://lite-short.com/api"

# Bot Username
BOT_USERNAME = "Terabox_Downloader_in_bot"
