import os
import time
import uuid
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import config

# Telegram Client Setup
app = Client(
    "terabox_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# MongoDB Setup
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
    
    # Reset daily limit after 24 hours
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
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as resp:
            data = await resp.json()
            if data.get("status") == "success":
                return data.get("shortenedUrl")
    return url

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text_split = message.text.split()
    
    # Handle verification via token
    if len(text_split) > 1:
        token = text_split[1]
        token_doc = tokens_col.find_one({"token": token, "user_id": user_id})
        if token_doc:
            users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": 3}})
            tokens_col.delete_one({"_id": token_doc["_id"]})
            await message.reply_text("✅ వెరిఫికేషన్ పూర్తయింది! మీకు మరో 3 డౌన్‌లోడ్‌లు లభించాయి. ఇప్పుడు మీ TeraBox లింక్‌ను పంపండి.")
            return
        else:
            await message.reply_text("❌ చెల్లని లేదా కాలం ముగిసిన వెరిఫికేషన్ లింక్.")
            return

    get_user_data(user_id)
    await message.reply_text(
        "👋 నమస్తే! నేను TeraBox Downloader Bot.\n\n"
        "📥 ఏదైనా TeraBox లింక్ పంపండి, నేను మీకు డైరెక్ట్ డౌన్‌లోడ్ చేసి ఇస్తాను.\n"
        "🔹 రోజుకు 2 డౌన్‌లోడ్‌లు పూర్తిగా ఉచితం.\n"
        "🔹 ఆ తర్వాత చిన్న వెరిఫికేషన్ ద్వారా మరో 3 డౌన్‌లోడ్‌లు అన్‌లాక్ చేసుకోవచ్చు!"
    )

@app.on_message(filters.regex(r"https?://.*(terabox|1024tera|freeterabox|teraboxapp)\.com/\S+"))
async def terabox_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    free_used = user.get("free_count", 0)
    bonus_left = user.get("bonus_count", 0)
    
    # Check download limits
    if free_used >= 2 and bonus_left <= 0:
        token = str(uuid.uuid4())
        tokens_col.insert_one({"token": token, "user_id": user_id, "created_at": time.time()})
        deep_link = f"https://t.me/{config.BOT_USERNAME}?start={token}"
        short_url = await get_shortlink(deep_link)
        
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 అదనపు డౌన్‌లోడ్‌లను అన్‌లాక్ చేయండి", url=short_url)]
        ])
        await message.reply_text(
            "⚠️ మీ రోజువారీ 2 ఉచిత డౌన్‌లోడ్‌లు పూర్తయ్యాయి!\n\n"
            "మరో 3 డౌన్‌లోడ్‌లు అన్‌లాక్ చేయడానికి క్రింది బటన్ నొక్కి చిన్న వెరిఫికేషన్ పూర్తి చేయండి:",
            reply_markup=btn
        )
        return

    # Update limit count
    if free_used < 2:
        users_col.update_one({"user_id": user_id}, {"$inc": {"free_count": 1}})
    else:
        users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": -1}})

    status_msg = await message.reply_text("⏳ మీ ఫైల్ లింక్ ప్రాసెస్ అవుతోంది... దయచేసి వేచి ఉండండి.")
    terabox_url = message.text.strip()
    
    # Fetch direct download link from API
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
                            [InlineKeyboardButton("🚀 Direct Download File", url=download_link)]
                        ])
                        await status_msg.edit_text(
                            f"🎬 **ఫైల్ పేరు:** `{file_name}`\n\nడౌన్‌లోడ్ చేయడానికి క్రింది బటన్ నొక్కండి:",
                            reply_markup=btn
                        )
                        return
        await status_msg.edit_text("❌ లింక్ నుండి ఫైల్ డౌన్‌లోడ్ పొందడం సాధ్యం కాలేదు. లింక్ చెక్ చేసి మళ్ళీ ప్రయత్నించండి.")
    except Exception as e:
        await status_msg.edit_text("⚠️ సర్వర్ రెస్పాన్స్ ఇవ్వడంలో సమస్య వచ్చింది. కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.")

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
  
