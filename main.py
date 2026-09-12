import asyncio

# Fix event loop for Python 3.12+ before importing Pyrogram
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.get_event_loop_policy().set_event_loop(loop)

import os
import time
import uuid
import urllib.parse
import aiohttp
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import config

# Initialize Telegram Client
app = Client(
    "terabox_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Initialize MongoDB
mongo_client = MongoClient(config.MONGO_URL)
db = mongo_client["terabox_db"]
users_col = db["users"]
tokens_col = db["verify_tokens"]

def get_user_data(user_id: int):
    user = users_col.find_one({"user_id": user_id})
    current_time = time.time()
    if not user:
        user = {
            "user_id": user_id,
            "free_count": 0,
            "bonus_count": 0,
            "last_reset": current_time
        }
        users_col.insert_one(user)
        return user

    if current_time - user.get("last_reset", 0) > 86400:
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"free_count": 0, "bonus_count": 0, "last_reset": current_time}}
        )
        user["free_count"] = 0
        user["bonus_count"] = 0
    return user

async def get_shortlink(url: str):
    encoded_url = urllib.parse.quote(url)
    api_url = f"{config.SHORTENER_URL}?api={config.SHORTENER_API}&url={encoded_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                data = await resp.json()
                if data.get("status") == "success" and data.get("shortenedUrl"):
                    return data.get("shortenedUrl")
    except Exception as e:
        print(f"Shortener error: {e}")
    return url

async def fetch_terabox_download(url: str):
    # Method 1: Primary TeraBox API
    api1 = f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={url.split('/')[-1]}"
    # Method 2: Alternate API
    api2 = f"https://teraboxvideodownloader.nepcoderdevs.workers.dev/?url={url}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # Try Method 1
        try:
            async with session.get(api1, timeout=15) as resp:
                data = await resp.json()
                if data and "download_link" in data:
                    return data.get("download_link"), data.get("file_name", "TeraBox_File")
                if data and "list" in data and len(data["list"]) > 0:
                    item = data["list"][0]
                    return item.get("dlink") or item.get("download_link"), item.get("server_filename", "TeraBox_File")
        except Exception:
            pass

        # Try Method 2
        try:
            async with session.get(api2, timeout=15) as resp:
                data = await resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    d_link = item.get("download_url") or item.get("direct_link")
                    if d_link:
                        return d_link, item.get("file_name", "TeraBox_File")
        except Exception:
            pass

    return None, None

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text_split = message.text.split()

    if len(text_split) > 1:
        token = text_split[1]
        token_doc = tokens_col.find_one({"token": token, "user_id": user_id})
        if token_doc:
            users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": 3}})
            tokens_col.delete_one({"_id": token_doc["_id"]})
            await message.reply_text("Verification successful! You received 3 additional downloads. Send your TeraBox link now.")
            return
        else:
            await message.reply_text("Invalid or expired verification token.")
            return

    get_user_data(user_id)
    await message.reply_text(
        "Welcome to TeraBox Downloader Bot!\n\n"
        "Send any TeraBox link to get direct download access.\n\n"
        "- 2 Free downloads daily.\n"
        "- Complete short verification to unlock 3 extra downloads!"
    )

@app.on_message(filters.text & filters.private & ~filters.command(["start"]))
async def terabox_handler(client: Client, message: Message):
    text = message.text.strip()
    
    if not any(domain in text.lower() for domain in ["terabox", "1024tera", "freeterabox", "terasharelink"]):
        await message.reply_text("Please send a valid TeraBox link.")
        return

    user_id = message.from_user.id
    user = get_user_data(user_id)

    free_used = user.get("free_count", 0)
    bonus_left = user.get("bonus_count", 0)

    # Monetization Check
    if free_used >= 2 and bonus_left <= 0:
        token = str(uuid.uuid4())
        tokens_col.insert_one({"token": token, "user_id": user_id, "created_at": time.time()})
        deep_link = f"https://t.me/{config.BOT_USERNAME}?start={token}"
        short_url = await get_shortlink(deep_link)

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("Unlock 3 Extra Downloads", url=short_url)]
        ])
        await message.reply_text(
            "Daily free download limit (2/2) reached!\n\n"
            "Click the button below to verify and unlock 3 additional downloads:",
            reply_markup=btn
        )
        return

    # Extract URL properly from text/forwarded messages
    words = text.split()
    terabox_url = next((w for w in words if "http" in w), text)

    status_msg = await message.reply_text("Processing your link... Please wait.")

    download_link, file_name = await fetch_terabox_download(terabox_url)

    if download_link:
        # Deduct / increase counter only on successful link retrieval
        if free_used < 2:
            users_col.update_one({"user_id": user_id}, {"$inc": {"free_count": 1}})
        else:
            users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": -1}})

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("Download File / Watch Online", url=download_link)]
        ])
        await status_msg.edit_text(
            f"File Name: `{file_name}`\n\nClick the button below to download:",
            reply_markup=btn
        )
    else:
        await status_msg.edit_text("Could not extract download link. TeraBox server may be blocking requests right now. Please try another link.")

# Web Server to satisfy Render port check
async def handle_ping(request):
    return web.Response(text="Bot is running live!")

async def start_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

async def run_bot():
    await start_server()
    await app.start()
    print("Bot is started successfully!")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(run_bot())
