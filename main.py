import asyncio

# Fix event loop for Python 3.12+ before importing Pyrogram
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.get_event_loop_policy().set_event_loop(loop)

import os
import time
import uuid
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
    api_url = f"{config.SHORTENER_URL}?api={config.SHORTENER_API}&url={url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                data = await resp.json()
                if data.get("status") == "success":
                    return data.get("shortenedUrl")
    except Exception:
        pass
    return url

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

    words = text.split()
    terabox_url = next((w for w in words if "http" in w), text)

    if free_used < 2:
        users_col.update_one({"user_id": user_id}, {"$inc": {"free_count": 1}})
    else:
        users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": -1}})

    status_msg = await message.reply_text("Processing your link... Please wait.")

    api_endpoint = f"https://teraboxvideodownloader.nepcoderdevs.workers.dev/?url={terabox_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint) as resp:
                data = await resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    download_link = item.get("download_url") or item.get("direct_link")
                    file_name = item.get("file_name", "TeraBox_File")

                    if download_link:
                        btn = InlineKeyboardMarkup([
                            [InlineKeyboardButton("Download File", url=download_link)]
                        ])
                        await status_msg.edit_text(
                            f"File Name: {file_name}\n\nClick the button below to download:",
                            reply_markup=btn
                        )
                        return
        await status_msg.edit_text("Could not extract download link. Please verify the URL.")
    except Exception:
        await status_msg.edit_text("Service is currently busy. Please try again later.")

# Web Server to satisfy Render port binding
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
