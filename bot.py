# bot.py (Final version with reliable file_id and full functionality)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

# IMPORTANT: Replace this placeholder with the actual file_id you got from your bot.
WELCOME_IMAGE_FILE_ID = "https://t.me/DESIARUNGAMERS/68" 

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- Bot Command and Message Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message with a photo and inline buttons."""
    user = update.effective_user
    
    # Create the inline keyboard buttons
    keyboard = [
        [InlineKeyboardButton("🔍 SEARCH MOVIES OR SERIES 🔍", callback_data="search_prompt")],
        [InlineKeyboardButton("📤 SHARE NOW 📤", switch_inline_query="Check out this awesome movie bot!")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # The welcome message text
    welcome_message = (
        f"Hey 👋 {user.first_name}!\n\n"
        "🍿 WELCOME TO THE MOVIE INFO ENGINE! 🍿\n\n"
        "You can search for any Movie or TV Series.\n\n"
        "Press the button below or just send me a name!"
    )
    
    # Send a photo using the super-reliable file_id
    await update.message.reply_photo(
        photo=WELCOME_IMAGE_FILE_ID,
        caption=welcome_message,
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and runs the appropriate action."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    if query.data == "search_prompt":
        await query.message.reply_text("Great! Send me the name of the movie or series you want to search for.")

async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Searches for the movie on OMDb and replies with the details."""
    movie_title = update.message.text
    api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={movie_title}"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        if data.get("Response") == "True":
            title = data.get("Title", "N/A")
            year = data.get("Year", "N/A")
            plot = data.get("Plot", "N/A")
            poster_url = data.get("Poster", "")
            imdb_rating = data.get("imdbRating", "N/A")
            genre = data.get("Genre", "N/A")

            # Use MarkdownV2 for better formatting control, but escape special characters
            # For simplicity, we'll stick to basic Markdown which is less strict.
            caption = (
                f"🎬 *{title}* ({year})\n\n"
                f"_{plot}_\n\n"
                f"⭐ *IMDb Rating:* {imdb_rating}\n"
                f"🎭 *Genre:* {genre}\n"
            )

            if poster_url and poster_url != "N/A":
                await update.message.reply_photo(
                    photo=poster_url,
                    caption=caption,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(caption, parse_mode='Markdown')
        else:
            error_message = data.get("Error", "Could not find that movie.")
            await update.message.reply_text(f"😞 Sorry, {error_message}")

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await update.message.reply_text("Sorry, I can't reach the movie database right now.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error('Update "%s" caused error "%s"', update, context.error)


# --- Main Function to Run the Bot ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("FATAL: TELEGRAM_TOKEN environment variable not set!")
        return
    if not OMDB_API_KEY:
        logger.error("FATAL: OMDB_API_KEY environment variable not set!")
        return
    if "PASTE_YOUR_FILE_ID_HERE" in WELCOME_IMAGE_FILE_ID:
        logger.error("FATAL: Please replace 'PASTE_YOUR_FILE_ID_HERE' in bot.py with your actual file_id.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))
    application.add_error_handler(error_handler)

    # Webhook setup for Render
    PORT = int(os.environ.get('PORT', 8443))
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')
    if WEBHOOK_URL:
        logger.info(f"Starting webhook on port {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        logger.info("Starting bot in polling mode for local testing")
        application.run_polling()

if __name__ == '__main__':
    main()
