import os
import re
from datetime import datetime, timezone

import asyncpg
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

ETH_ADDRESS = "0x500cb137348438cd2fc389ac6d56b170e4f5f8cf"
SOL_ADDRESS = "2mk8Ny9xXdWVjEzVUnDDM8saTHv5gXctBMassAhwKfGf"

DATABASE_URL = os.environ["DATABASE_URL"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as con:
        await con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                telegram_id BIGINT PRIMARY KEY,
                chain TEXT NOT NULL DEFAULT 'both',
                copytrade BOOLEAN NOT NULL DEFAULT FALSE,
                autotrade BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy Trade", callback_data="copy"),
         InlineKeyboardButton("🤖 Auto Trade", callback_data="auto")],
        [InlineKeyboardButton("💰 Wallet", callback_data="wallet"),
         InlineKeyboardButton("📥 Import Wallet", callback_data="import")],
        [InlineKeyboardButton("🔑 Keys", callback_data="keys"),
         InlineKeyboardButton("📌 Pointers", callback_data="pointers")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("📖 Bot Guide", callback_data="guide")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    now = datetime.now(timezone.utc)
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO users(telegram_id, username, created_at)
               VALUES($1,$2,$3)
               ON CONFLICT (telegram_id) DO UPDATE SET username=EXCLUDED.username""",
            u.id, u.username or "", now
        )
        await con.execute(
            "INSERT INTO settings(telegram_id) VALUES($1) ON CONFLICT DO NOTHING", u.id
        )
    await update.message.reply_text("🤖 Trading Bot\n\nChoose an option below.", reply_markup=menu())

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data in ("copy", "auto"):
        context.user_data["awaiting"] = data
        await q.message.reply_text(
            "🤖 Autotrade\n\nSend the wallet address you'd like to enable autotrade for."
        )
    elif data == "wallet":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Create Wallet", callback_data="create")],
            [InlineKeyboardButton("📥 Import Wallet", callback_data="import")],
            [InlineKeyboardButton("◀️ Back", callback_data="back")],
        ])
        await q.message.reply_text(
            f"💰 Your Wallets\n\nEthereum\n`{ETH_ADDRESS}`\n\nSolana\n`{SOL_ADDRESS}`",
            parse_mode="Markdown", reply_markup=kb
        )
    elif data == "create":
        await q.message.reply_text(
            f"💰 Wallets\n\nEthereum\n`{ETH_ADDRESS}`\n\nSolana\n`{SOL_ADDRESS}`",
            parse_mode="Markdown"
        )
    elif data == "import":
        await q.message.reply_text(
            "📥 Import Wallet\n\nFor this starter, add a public wallet address only.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Public Wallet Address", callback_data="public_address")],
                [InlineKeyboardButton("◀️ Back", callback_data="back")]
            ])
        )
    elif data == "public_address":
        context.user_data["awaiting"] = "public_address"
        await q.message.reply_text("Send the public wallet address you'd like to add.")
    elif data in ("keys", "pointers"):
        context.user_data["awaiting"] = data
        label = "Keys" if data == "keys" else "Pointers"
        await q.message.reply_text(
            f"{'🔑' if data == 'keys' else '📌'} {label}\n\n"
            "Send the text you want the bot to save under this category."
        )
    elif data == "settings":
        await q.message.reply_text("⚙️ Settings\n\nETH + Solana are supported simultaneously.")
    elif data == "guide":
        await q.message.reply_text(
            "📖 Bot Guide\n\n"
            "Wallet displays the configured ETH and Solana addresses.\n"
            "Copy Trade and Auto Trade begin with a wallet-address prompt.\n"
            "Keys and Pointers are generic text-collection categories."
        )
    elif data == "back":
        await q.message.reply_text("🤖 Trading Bot", reply_markup=menu())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        await update.message.reply_text("Choose an option:", reply_markup=menu())
        return

    text = update.message.text.strip()
    if not text or len(text) > 4000:
        await update.message.reply_text("Please send a non-empty message up to 4000 characters.")
        return

    u = update.effective_user
    async with pool.acquire() as con:
        await con.execute(
            """INSERT INTO submissions(telegram_id, kind, text, created_at)
               VALUES($1,$2,$3,$4)""",
            u.id, awaiting, text, datetime.now(timezone.utc)
        )
        if awaiting == "auto":
            await con.execute(
                "UPDATE settings SET autotrade=TRUE WHERE telegram_id=$1", u.id
            )
        elif awaiting == "copy":
            await con.execute(
                "UPDATE settings SET copytrade=TRUE WHERE telegram_id=$1", u.id
            )

    context.user_data.pop("awaiting", None)
    await update.message.reply_text("✅ Received and saved.", reply_markup=menu())

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Not authorized.")
        return
    async with pool.acquire() as con:
        rows = await con.fetch("""
            SELECT id, telegram_id, kind, text, created_at
            FROM submissions ORDER BY id DESC LIMIT 50
        """)
    if not rows:
        await update.message.reply_text("No submissions yet.")
        return
    out = ["🛠 Admin — latest submissions"]
    for r in rows:
        out.append(f"\n#{r['id']} | user {r['telegram_id']} | {r['kind']}\n{r['text']}\n{r['created_at']}")
    # Telegram message limit is ~4096 chars.
    await update.message.reply_text("\n".join(out)[:4000])

async def post_init(application):
    await init_db()

async def post_shutdown(application):
    global pool
    if pool:
        await pool.close()

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
