import sqlite3
import qrcode
import io
import logging
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters, ContextTypes

# --- [1. YOUR CUSTOM DATA] ---
TOKEN = "8587168502:AAH1VIWg1KMV3uYXvybdFU_5khxCSiYpxeA"
ADMIN_ID = 1328710454
CHANNEL_ID = -1003750190204 
UPI_ID = "7693971975@ybl"

# Your Price -> Video Credit Mapping
PLANS = {
    "9":  {"stars": 5,  "credits": 5,   "name": "📦 Starter"},
    "19": {"stars": 10, "credits": 10,  "name": "🚀 Standard"},
    "29": {"stars": 15, "credits": 25,  "name": "💎 Plus"},
    "39": {"stars": 20, "credits": 40,  "name": "🔥 Premium"},
    "49": {"stars": 25, "credits": 50,  "name": "👑 VVIP"}
}

# Your Video Catalog from Channel
CATALOG = {
    "vid1": {"name": "🎬 Premium Video 1", "msg_id": 316},
}

# --- [2. DATABASE & QR SETUP] ---
def init_db():
    conn = sqlite3.connect('hut1_master.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

def make_qr(user_id, amount):
    upi_url = f"upi://pay?pa={UPI_ID}&pn=Hut1&am={amount}&cu=INR&tn=HUT1_USER_{user_id}"
    qr = qrcode.make(upi_url)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    buf.seek(0)
    return buf

# --- [3. CORE LOGIC] ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_db()
    conn = sqlite3.connect('hut1_master.db'); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
    balance = c.fetchone()[0]
    conn.close()

    text = (f"💎 **Welcome to Hut1 Entertainment**\n\n"
            f"👤 **Your ID:** `{user_id}`\n"
            f"💰 **Balance:** `{balance} Credits`\n\n"
            "Select an option below to get started!")
    btns = [[InlineKeyboardButton("🎬 Watch Catalog", callback_data='catalog')],
            [InlineKeyboardButton("💳 Buy Credits", callback_data='buy_menu')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [[InlineKeyboardButton(f"{v['name']} (1 💎)", callback_data=f"play_{k}")] for k, v in CATALOG.items()]
    btns.append([InlineKeyboardButton("🔙 Back", callback_data='home')])
    await update.callback_query.edit_message_text("🎞️ **Hut1 Catalog**\nVideos delete in 6 hours for privacy.", 
                                                 reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

async def play_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    vid_key = query.data.split("_")[1]
    
    conn = sqlite3.connect('hut1_master.db'); c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)); res = c.fetchone()
    
    if res and res[0] > 0:
        c.execute("UPDATE users SET credits = credits - 1 WHERE user_id=?", (user_id,))
        conn.commit(); conn.close()
        
        sent = await context.bot.copy_message(
            chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=CATALOG[vid_key]['msg_id'],
            protect_content=True, caption="🛡️ **Protected by Hut1**\n_Forwarding disabled. Deleting in 6 hours._"
        )
        # Auto-delete job
        context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(user_id, sent.message_id), 21600)
        await query.answer("Enjoy! Video unlocked. 🍿")
    else:
        conn.close()
        await query.answer("❌ You need more credits!", show_alert=True)

# --- [4. PAYMENT HANDLERS] ---
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [[InlineKeyboardButton(f"₹{k} - {v['credits']} Videos", callback_data=f"pay_{k}")] for k, v in PLANS.items()]
    await update.callback_query.edit_message_text("💳 **Choose your pack:**", reply_markup=InlineKeyboardMarkup(btns))

async def pay_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = update.callback_query.data.split("_")[1]
    btns = [[InlineKeyboardButton("⭐ Stars (Instant Auto)", callback_data=f"star_{price}")],
            [InlineKeyboardButton("📲 PhonePe (QR Manual)", callback_data=f"qr_{price}")],
            [InlineKeyboardButton("🔙 Back", callback_data='buy_menu')]]
    await update.callback_query.edit_message_text(f"How would you like to pay ₹{price}?", reply_markup=InlineKeyboardMarkup(btns))

async def send_star_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = update.callback_query.data.split("_")[1]
    plan = PLANS[price]
    await context.bot.send_invoice(
        chat_id=update.effective_user.id, title=f"Hut1 Credits",
        description=f"Add {plan['credits']} credits to watch premium videos.",
        payload=f"stars_{plan['credits']}", provider_token="", currency="XTR",
        prices=[LabeledPrice("Stars", plan['stars'])]
    )

async def send_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = update.callback_query.data.split("_")[1]
    user_id = update.effective_user.id
    qr_img = make_qr(user_id, price)
    await context.bot.send_photo(user_id, qr_img, caption=f"📸 **Scan to Pay ₹{price}**\n\n1. Use PhonePe/GPay\n2. **Send screenshot here** for approval.")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID: return
    # Admin Buttons
    btns = [[InlineKeyboardButton(f"✅ Add {v['credits']}", callback_data=f"adm_{v['credits']}_{update.effective_user.id}")] for k,v in PLANS.items()]
    btns.append([InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{update.effective_user.id}")])
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, f"📩 Receipt from `{update.effective_user.id}`", reply_markup=InlineKeyboardMarkup(btns))
    await update.message.reply_text("✅ Receipt received! Admin is verifying your payment.")

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data.split("_")
    if data[1] == "rej":
        await context.bot.send_message(int(data[2]), "❌ Payment rejected. Please contact support.")
        await update.callback_query.edit_message_caption("Rejected.")
    else:
        creds, uid = int(data[1]), int(data[2])
        conn = sqlite3.connect('hut1_master.db'); c = conn.cursor()
        c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (creds, uid))
        conn.commit(); conn.close()
        await context.bot.send_message(uid, f"🎉 **Success!** {creds} credits added. Go to Catalog to watch!")
        await update.callback_query.edit_message_caption(f"✅ Approved {creds} credits.")

# --- [5. RUNNER] ---
if __name__ == "__main__":
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(catalog, pattern='^catalog$|^home$'))
    app.add_handler(CallbackQueryHandler(buy_menu, pattern='^buy_menu$'))
    app.add_handler(CallbackQueryHandler(pay_options, pattern='^pay_'))
    app.add_handler(CallbackQueryHandler(send_star_invoice, pattern='^star_'))
    app.add_handler(CallbackQueryHandler(send_qr, pattern='^qr_'))
    app.add_handler(CallbackQueryHandler(play_video, pattern='^play_'))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern='^adm_'))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(PreCheckoutQueryHandler(lambda u, c: u.pre_checkout_query.answer(ok=True)))
    # For Stars Success
    async def star_success(u, c):
        creds = int(u.message.successful_payment.invoice_payload.split("_")[1])
        conn = sqlite3.connect('hut1_master.db'); c_db = conn.cursor()
        c_db.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (creds, u.effective_user.id))
        conn.commit(); conn.close()
        await u.message.reply_text(f"⭐ Credits Added: {creds}!")
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, star_success))
    
    print("🚀 Hut1 is Online! Go to your bot and type /start")
    app.run_polling()
  
