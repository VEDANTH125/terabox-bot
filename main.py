import asyncio

# Fix event loop for Pyrogram on modern Python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.get_event_loop_policy().set_event_loop(loop)

import os
import re
import time
import uuid
import urllib.parse
import aiohttp
import aiofiles
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pymongo import MongoClient
import config

# Configuration Variables
ADMIN_ID = 8266084614
ADMIN_USERNAME = "MrXman5"
UPI_ID = "Vedanth1439@ybl"

# Initialize Pyrogram Bot Client
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

def get_user_data(user_id: int, first_name: str = "User"):
    user = users_col.find_one({"user_id": user_id})
    current_time = time.time()
    if not user:
        user = {
            "user_id": user_id,
            "name": first_name,
            "free_count": 0,
            "bonus_count": 0,
            "invites": 0,
            "coins": 0,
            "is_premium": False,
            "premium_expiry": 0,
            "last_reset": current_time
        }
        users_col.insert_one(user)
        return user

    # Check premium expiry
    if user.get("is_premium") and current_time > user.get("premium_expiry", 0):
        users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
        user["is_premium"] = False

    # 24-hour reset for free daily limits
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

async def fetch_terabox_api(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    endpoints = [
        f"https://yt-video-production.up.railway.app/terabox?url={url}",
        f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={url.split('/')[-1]}",
        f"https://terabox-api.grayhat.workers.dev/?url={url}",
        f"https://teraboxvideodownloader.nepcoderdevs.workers.dev/?url={url}"
    ]

    async with aiohttp.ClientSession(headers=headers) as session:
        for ep in endpoints:
            try:
                async with session.get(ep, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Structure 1
                        if data and "download_url" in data:
                            return data.get("download_url"), data.get("file_name", "TeraBox_Video.mp4")
                        if data and "direct_link" in data:
                            return data.get("direct_link"), data.get("file_name", "TeraBox_Video.mp4")
                        # Structure 2 (List format)
                        if data and "list" in data and len(data["list"]) > 0:
                            item = data["list"][0]
                            dlink = item.get("dlink") or item.get("download_link") or item.get("direct_link")
                            fname = item.get("server_filename") or item.get("filename", "TeraBox_Video.mp4")
                            if dlink:
                                return dlink, fname
                        # Structure 3 (Nested response)
                        if data and "response" in data and len(data["response"]) > 0:
                            item = data["response"][0]
                            return item.get("resolutions", {}).get("Fast Download") or item.get("dlink"), item.get("server_filename", "TeraBox_Video.mp4")
            except Exception:
                continue

    return None, None

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Premium", callback_data="btn_premium"), InlineKeyboardButton("📩 Share Bot", callback_data="btn_share")],
        [InlineKeyboardButton("ℹ️ About Bot", callback_data="btn_about")],
        [InlineKeyboardButton("🎁 Invite & Earn", callback_data="btn_invite")],
        [InlineKeyboardButton("💰 Earn Money from Bot", callback_data="btn_earn")]
    ])

PLANS = {
    "12": {
        "name": "Basic Plan",
        "price": "12",
        "days": 7,
        "validity": "7 Days (1 Week)",
        "desc": "Best for short-term downloads with zero ads."
    },
    "29": {
        "name": "Pro Plan",
        "price": "29",
        "days": 30,
        "validity": "30 Days (1 Month)",
        "desc": "Perfect for regular daily users watching movies/series."
    },
    "49": {
        "name": "Proplus Plan",
        "price": "49",
        "days": 60,
        "validity": "60 Days (2 Months)",
        "desc": "Value pack with two months of unlimited high speed access."
    },
    "139": {
        "name": "Iconic Plan",
        "price": "139",
        "days": 180,
        "validity": "180 Days (6 Months)",
        "desc": "Half-yearly access with top priority queue and zero waiting."
    },
    "219": {
        "name": "Ultra Plan",
        "price": "219",
        "days": 365,
        "validity": "365 Days (1 Full Year)",
        "desc": "Maximum savings! Unlimited downloads for a full year."
    }
}

# Admin Command: /addpremium <user_id> <days>
@app.on_message(filters.command("addpremium") & filters.user(ADMIN_ID))
async def add_premium_cmd(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("⚠️ **Usage:** `/addpremium <user_id> <days>`\nExample: `/addpremium 123456789 30`")
        return

    try:
        target_user_id = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.reply_text("❌ User ID and Days must be valid numbers.")
        return

    seconds_to_add = days * 86400
    current_time = time.time()
    user = users_col.find_one({"user_id": target_user_id})

    if user and user.get("is_premium") and user.get("premium_expiry", 0) > current_time:
        new_expiry = user.get("premium_expiry") + seconds_to_add
    else:
        new_expiry = current_time + seconds_to_add

    users_col.update_one(
        {"user_id": target_user_id},
        {"$set": {"is_premium": True, "premium_expiry": new_expiry}},
        upsert=True
    )

    await message.reply_text(f"✅ User `{target_user_id}` has been granted **{days} days of Premium** successfully!")

    # Notify target user
    try:
        await client.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 **Premium Subscription Activated!**\n\n"
                f"⏳ **Validity:** {days} Days\n"
                f"⚡ You can now enjoy unlimited downloads without any limits or verification tokens!"
            )
        )
    except Exception as e:
        print(f"Could not notify user: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    text_split = message.text.split()

    if len(text_split) > 1:
        param = text_split[1]
        
        if param.startswith("verify_"):
            token = param.replace("verify_", "")
            token_doc = tokens_col.find_one({"token": token, "user_id": user_id})
            if token_doc:
                users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": 3}})
                tokens_col.delete_one({"_id": token_doc["_id"]})
                await message.reply_text("✅ Verification successful! You received 3 additional downloads. Send your TeraBox link now.")
                return
            else:
                await message.reply_text("❌ Invalid or expired verification link.")
                return

        elif param.startswith("invite_"):
            try:
                referrer_id = int(param.replace("invite_", ""))
                if referrer_id != user_id and not users_col.find_one({"user_id": user_id}):
                    users_col.update_one({"user_id": referrer_id}, {"$inc": {"invites": 1, "coins": 1}})
            except Exception:
                pass

    user = get_user_data(user_id, first_name)
    welcome_text = (
        f"Hello, {first_name}!\n\n"
        "Welcome to TeraBox Download Bot! 😊\n\n"
        "1. Send me a TeraBox link.\n"
        "2. Relax while I process your request.\n\n"
        f"🎯 Your Earning Stats:\n"
        f"├ Invites: {user.get('invites', 0)}\n"
        f"└ Coins: {user.get('coins', 0)}"
    )

    photo_banner = "https://i.ibb.co/vzjC4wY/invite-banner.png"
    try:
        await message.reply_photo(photo=photo_banner, caption=welcome_text, reply_markup=get_main_keyboard())
    except Exception:
        await message.reply_text(text=welcome_text, reply_markup=get_main_keyboard())

@app.on_callback_query()
async def callback_router(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    first_name = query.from_user.first_name or "User"
    user = get_user_data(user_id, first_name)
    bot_username = config.BOT_USERNAME

    if data == "btn_home":
        welcome_text = (
            f"Hello, {first_name}!\n\n"
            "Welcome to TeraBox Download Bot! 😊\n\n"
            "1. Send me a TeraBox link.\n"
            "2. Relax while I process your request.\n\n"
            f"🎯 Your Earning Stats:\n"
            f"├ Invites: {user.get('invites', 0)}\n"
            f"└ Coins: {user.get('coins', 0)}"
        )
        try:
            await query.message.edit_text(welcome_text, reply_markup=get_main_keyboard())
        except Exception:
            await query.message.edit_caption(caption=welcome_text, reply_markup=get_main_keyboard())

    elif data == "btn_premium":
        premium_text = (
            "💎 **Premium Benefits**\n\n"
            "🚀 Lightning Fast Downloads\n"
            "⚡ Priority Queue Access\n"
            "🎬 Original Quality Downloads\n"
            "🎯 Priority Support\n"
            "📁 Download Files Up to 4GB\n"
            "🤖 Premium on ALL Bots\n"
            "🚫 No Ads\n"
            "🎟️ No Token System\n\n"
            "──────────────────\n\n"
            "◈ **Choose Your Premium Plan:**\n\n"
            "Basic Plan - ₹12\n"
            "Pro Plan - ₹29\n"
            "Proplus plan - ₹49\n"
            "Iconic plan - ₹139\n"
            "Ultra Plan - ₹219\n\n"
            "──────────────────\n\n"
            "🤖 One Premium Subscription =\n"
            "Access to ALL Terabox Bots!\n\n"
            "💡 Click a button below to view plan details & payment instructions!"
        )
        prem_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("₹12 = 7 days", callback_data="plan_12")],
            [InlineKeyboardButton("₹29 = 30 days", callback_data="plan_29")],
            [InlineKeyboardButton("₹49 = 60 days", callback_data="plan_49")],
            [InlineKeyboardButton("₹139 = 6 Months", callback_data="plan_139")],
            [InlineKeyboardButton("₹219 = 1 Year", callback_data="plan_219")],
            [InlineKeyboardButton("« Back", callback_data="btn_home")]
        ])
        try:
            await query.message.edit_text(premium_text, reply_markup=prem_keyboard)
        except Exception:
            await query.message.edit_caption(caption=premium_text, reply_markup=prem_keyboard)

    elif data.startswith("plan_"):
        plan_id = data.replace("plan_", "")
        plan = PLANS.get(plan_id, PLANS["12"])
        price = plan["price"]

        # Dynamic locked QR Code URL
        upi_payload = f"upi://pay?pa={UPI_ID}&pn=TeraBoxBot&am={price}&cu=INR"
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={urllib.parse.quote(upi_payload)}"

        detail_text = (
            f"👑 **{plan['name']} - ₹{price}**\n\n"
            f"⏳ **Validity:** {plan['validity']}\n"
            f"📝 **Details:** {plan['desc']}\n\n"
            f"💳 **UPI ID:** `{UPI_ID}`\n"
            f"🆔 **Your Telegram ID:** `{user_id}`\n\n"
            "──────────────────\n"
            "📌 **How to Complete Payment:**\n"
            "1. Scan the QR code above or copy the UPI ID and pay via PhonePe / Google Pay / Paytm.\n"
            f"2. After payment, send the **Payment Screenshot** along with your **ID (`{user_id}`)** by clicking the button below.\n\n"
            "⚠️ Please pay the exact amount for faster activation."
        )

        detail_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Send Screenshot to Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
            [InlineKeyboardButton("« Back to Plans", callback_data="btn_premium")]
        ])

        try:
            await query.message.delete()
            await query.message.reply_photo(
                photo=qr_image_url,
                caption=detail_text,
                reply_markup=detail_kb
            )
        except Exception:
            await query.message.reply_text(detail_text, reply_markup=detail_kb)

    elif data == "btn_about":
        about_text = (
            "🤖 **Codezora_terabot - Bot Information**\n\n"
            "🔢 Version: 12.7.0\n"
            "🏷 Bot Index: CT06\n"
            "⚡ Platform: CodeZora V3\n"
            f"👑 Owned by: @{bot_username}\n\n"
            "📊 **Bot Statistics:**\n"
            "├ 👥 Users: 2,209\n"
            "├ 👥 Groups: 1\n"
            "└ 📩 Total Downloads: 26,583\n\n"
            "✨ **Features:**\n"
            "├ ✅ TeraBox File Downloads\n"
            "├ ✅ Fast & Reliable\n"
            "├ ✅ Premium Plans Available\n"
            "└ ✅ Referral Rewards System"
        )
        try:
            await query.message.edit_text(about_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Start", callback_data="btn_home")]]))
        except Exception:
            await query.message.edit_caption(caption=about_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Start", callback_data="btn_home")]]))

    elif data == "btn_invite":
        invite_link = f"https://t.me/{bot_username}?start=invite_{user_id}"
        invite_text = (
            "🎁 **Invite & Earn**\n\n"
            "Welcome to the referral program!\n"
            "Invite your friends and earn rewards.\n\n"
            "💰 **Earn 1 coin for every invite!**\n\n"
            "🎯 **Your Stats:**\n"
            f"├ Invites: {user.get('invites', 0)}\n"
            f"└ Coins: {user.get('coins', 0)}\n\n"
            f"🔗 **Your Invite Link:**\n`{invite_link}`\n\n"
            "👆 Tap to copy and share with friends!"
        )
        invite_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Share to Chat", url=f"https://t.me/share/url?url={invite_link}&text=Fastest%20TeraBox%20Downloader%20Bot!")],
            [InlineKeyboardButton("« Back to Start", callback_data="btn_home")]
        ])
        try:
            await query.message.edit_text(invite_text, reply_markup=invite_kb)
        except Exception:
            await query.message.edit_caption(caption=invite_text, reply_markup=invite_kb)

    elif data == "btn_share":
        share_link = f"https://t.me/{bot_username}?start=invite_{user_id}"
        share_text = (
            "🔗 **Share Your Invite Link:**\n\n"
            f"`{share_link}`\n\n"
            "👆 Tap on link to Copy\n\n"
            "📖 **How to Share:**\n"
            "1. Click the Share to Chat button below to send your invite directly to a chat.\n"
            "2. Copy the link and share it with friends.\n\n"
            "🎯 Invite friends to earn a coin!"
        )
        share_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Share to Chat", url=f"https://t.me/share/url?url={share_link}&text=Fastest%20TeraBox%20Downloader%20Bot!")],
            [InlineKeyboardButton("« Back to Start", callback_data="btn_home")]
        ])
        try:
            await query.message.edit_text(share_text, reply_markup=share_kb)
        except Exception:
            await query.message.edit_caption(caption=share_text, reply_markup=share_kb)

    elif data == "btn_earn":
        invite_link = f"https://t.me/{bot_username}?start=invite_{user_id}"
        earn_text = (
            "💰 **Earn Money from Bot**\n\n"
            "**2 Ways to Earn:**\n\n"
            "1️⃣ **Invite & Earn Coins**\n"
            "├ Share your invite link\n"
            "├ Earn 1 coin per user\n"
            "└ Convert coins to cash\n\n"
            f"**Your Invite Link:**\n`{invite_link}`\n\n"
            "2️⃣ **Share Promo Code**\n"
            "├ Users get 10% discount\n"
            "├ You earn 5% of plan price\n"
            "└ Withdraw anytime\n\n"
            "💡 You can do both to maximize earnings!"
        )
        try:
            await query.message.edit_text(earn_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Start", callback_data="btn_home")]]))
        except Exception:
            await query.message.edit_caption(caption=earn_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Start", callback_data="btn_home")]]))

@app.on_message(filters.text & filters.private & ~filters.command(["start", "addpremium"]))
async def process_terabox_link(client: Client, message: Message):
    text = message.text.strip()
    url_match = re.search(r"(https?://[^\s]+)", text)
    if not url_match or not any(x in url_match.group(1).lower() for x in ["terabox", "1024tera", "freeterabox", "terasharelink"]):
        return

    terabox_url = url_match.group(1)
    user_id = message.from_user.id
    user = get_user_data(user_id, message.from_user.first_name or "User")

    is_premium = user.get("is_premium", False)
    free_used = user.get("free_count", 0)
    bonus_left = user.get("bonus_count", 0)

    # Daily Limit Enforcement
    if not is_premium and free_used >= 2 and bonus_left <= 0:
        token = str(uuid.uuid4())[:8]
        tokens_col.insert_one({"token": token, "user_id": user_id, "created_at": time.time()})
        deep_link = f"https://t.me/{config.BOT_USERNAME}?start=verify_{token}"
        short_url = await get_shortlink(deep_link)

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Unlock 3 Extra Downloads", url=short_url)],
            [InlineKeyboardButton("⭐ Buy Premium (Unlimited)", callback_data="btn_premium")]
        ])
        await message.reply_text(
            f"ℹ️ **Daily Download Info**\n\n"
            f"• Used today: 2/2\n"
            f"• Remaining: 0\n"
            f"🌟 Upgrade to Premium for unlimited downloads!\n\n"
            f"⚠️ Daily free limit reached! Click below to verify via shortener or upgrade to premium:",
            reply_markup=btn
        )
        return

    used_display = "Unlimited" if is_premium else f"{min(free_used, 2)}/2"
    rem_display = "Unlimited" if is_premium else f"{max(0, 2 - free_used) + bonus_left}"
    info_msg = await message.reply_text(
        f"ℹ️ **Daily Download Info**\n\n"
        f"• Used today: {used_display}\n"
        f"• Remaining: {rem_display}\n"
        f"🌟 Upgrade to Premium for unlimited downloads!\n\n"
        f"🔄 Processing your request..."
    )

    download_link, file_name = await fetch_terabox_api(terabox_url)

    if not download_link:
        await info_msg.edit_text("❌ Could not extract download link. File might be deleted or server is temporarily busy.")
        return

    if not is_premium:
        if free_used < 2:
            users_col.update_one({"user_id": user_id}, {"$inc": {"free_count": 1}})
        else:
            users_col.update_one({"user_id": user_id}, {"$inc": {"bonus_count": -1}})

    # Direct Video Stream / Upload Delivery with Auto-Delete in 3 Hours
    try:
        temp_file = f"download_{user_id}_{int(time.time())}.mp4"
        async with aiohttp.ClientSession() as session:
            async with session.get(download_link, timeout=60) as resp:
                if resp.status == 200:
                    async with aiofiles.open(temp_file, mode='wb') as f:
                        await f.write(await resp.read())

                    caption_text = (
                        f"🎬 **File Name:** `{file_name}`\n\n"
                        f"⚠️ **Notice:** This video will automatically expire & delete in **3 Hours** for copyright safety.\n"
                        f"📌 Please forward or save this video to your saved messages/chats now!\n\n"
                        f"⚡ Delivered via @{config.BOT_USERNAME}"
                    )

                    sent_msg = await client.send_video(
                        chat_id=message.chat.id,
                        video=temp_file,
                        caption=caption_text,
                        reply_to_message_id=message.id
                    )

                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    await info_msg.delete()

                    # Background task to delete video after 3 hours (10800 seconds)
                    async def delete_after_delay(chat_id, msg_id):
                        await asyncio.sleep(10800)
                        try:
                            await client.delete_messages(chat_id=chat_id, message_ids=msg_id)
                        except Exception as e:
                            print(f"Auto-delete error: {e}")

                    asyncio.create_task(delete_after_delay(sent_msg.chat.id, sent_msg.id))
                    return
    except Exception as e:
        print(f"Direct stream upload error: {e}")

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Direct Download / Stream", url=download_link)]
    ])
    await info_msg.edit_text(
        f"🎬 **File Name:** `{file_name}`\n\n"
        f"⚠️ **Notice:** Direct link / stream will expire soon. Please save/download promptly.\n\n"
        f"Click below to watch or download directly:",
        reply_markup=btn
    )

# Render Port Binding
async def handle_ping(request):
    return web.Response(text="Bot is live 24/7!")

async def start_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def run_bot():
    await start_server()
    await app.start()
    print("Bot started successfully!")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(run_bot())
