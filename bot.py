# bot.py (Version 4: The Complete Professional Bot)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# --- Configuration from Environment Variables ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL") # Your PUBLIC channel (e.g., @mychannel)
DATABASE_CHANNEL_ID = os.environ.get("DATABASE_CHANNEL_ID") # Your PRIVATE channel ID (e.g., -1001...)
WELCOME_IMAGE_FILE_ID = os.environ.get("WELCOME_IMAGE_FILE_ID")

# --- Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Simple "Database" Mapping ---
# This maps a movie's IMDb ID to a Message ID in your DATABASE_CHANNEL_ID
# You must manually find the Message ID for each file you post in your private channel.
# To find a message ID, forward the message to a bot like @userinfobot
FILE_MAP = {
    "tt0133093": 2,  # Example: The Matrix -> Message ID 2 in your database channel
    "tt1375666": 3,  # Example: Inception -> Message ID 3
    "tt0468569": 4,  # Example: The Dark Knight -> Message ID 4
    # Add more movies here...
}

# --- Middleware & Handlers ---

async def check_user_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of the required channel."""
    if not UPDATES_CHANNEL: return True
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATES_CHANNEL, user_id=user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except (BadRequest, Forbidden):
        logger.error(f"Error checking membership for {user_id} in {UPDATES_CHANNEL}. Bot might not be admin.", exc_info=True)
        return False # Fail safely

async def force_subscribe_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, handler_func):
    """Wrapper that enforces channel subscription before executing a command."""
    if await check_user_membership(update, context):
        await handler_func(update, context)
    else:
        channel_link = f"https://t.me/{UPDATES_CHANNEL.lstrip('@')}"
        keyboard = [[InlineKeyboardButton("📢 JOIN CHANNEL 📢", url=channel_link)], [InlineKeyboardButton("🔄 Retry 🔄", callback_data="check_join")]]
        await update.effective_message.reply_text(
            "**You must join our channel to use this bot\\!**\n\nPlease join and click Retry\\.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await force_subscribe_wrapper(update, context, start_action)

async def start_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The actual start command logic."""
    keyboard = [[InlineKeyboardButton("🔍 Search Movies", switch_inline_query_current_chat="")]]
    await update.effective_message.reply_photo(
        photo=WELCOME_IMAGE_FILE_ID,
        caption=f"Welcome, {update.effective_user.first_name}\\!\n\nUse the button below to search for a movie\\.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await force_subscribe_wrapper(update, context, search_action)

async def search_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages to search for movies."""
    query = update.message.text
    api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&s={query}"
    try:
        response = requests.get(api_url)
        data = response.json()
        if data.get("Response") == "True":
            results = data.get("Search", [])
            keyboard = []
            for movie in results[:5]: # Show top 5 results
                button = InlineKeyboardButton(
                    f"🎬 {movie['Title']} ({movie['Year']})",
                    callback_data=f"select_{movie['imdbID']}"
                )
                keyboard.append([button])
            if keyboard:
                await update.message.reply_text("Here's what I found:", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text("No results found.")
        else:
            await update.message.reply_text("Couldn't find that movie. Please try another title.")
    except Exception as e:
        logger.error("Error during movie search", exc_info=True)
        await update.message.reply_text("Sorry, an error occurred during search.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_join":
        if await check_user_membership(update, context):
            await query.message.delete()
            await start_action(update, context)
        else:
            await query.answer("You still haven't joined the channel.", show_alert=True)
            
    elif data.startswith("select_"):
        imdb_id = data.split("_")[1]
        if imdb_id in FILE_MAP:
            message_id = FILE_MAP[imdb_id]
            try:
                await context.bot.forward_message(
                    chat_id=query.from_user.id,
                    from_chat_id=DATABASE_CHANNEL_ID,
                    message_id=message_id
                )
                await query.edit_message_text(f"✅ File sent for IMDb ID: {imdb_id}")
            except Exception as e:
                logger.error(f"Failed to forward message {message_id} from {DATABASE_CHANNEL_ID}", exc_info=True)
                await query.edit_message_text("❌ Sorry, I couldn't retrieve the file right now.")
        else:
            await query.edit_message_text("❌ Sorry, I don't have the file for the selected movie.")

def main():
    """Starts the bot."""
    # Pre-run checks for essential environment variables
    for var in ["TELEGRAM_TOKEN", "OMDB_API_KEY", "UPDATES_CHANNEL", "DATABASE_CHANNEL_ID", "WELCOME_IMAGE_FILE_ID"]:
        if not os.environ.get(var):
            logger.error(f"FATAL: Environment variable {var} is not set.")
            return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movies))
    application.add_handler(CallbackQueryHandler(button_handler))

    PORT = int(os.environ.get('PORT', 8443))
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == '__main__':
    main()
