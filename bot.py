# bot.py (Version 4 - Refined UI with Button)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = (
        f"Hi {user.first_name}! 🍿\n\n"
        "I am your modern Movie Info Bot, powered by TMDB!\n\n"
        "Just send me the name of any movie or TV show to get started."
    )
    await update.message.reply_text(welcome_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_API_KEY}"
    }
    
    search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
    
    try:
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()

        if not search_data.get("results"):
            await update.message.reply_text("😞 Sorry, I couldn't find any movie with that name.")
            return

        top_result = search_data["results"][0]
        movie_id = top_result["id"]
        
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()

        # --- Data Extraction (Modified for new format) ---
        title = data.get("title", "N/A")
        vote_average = data.get("vote_average", 0)
        genres = ", ".join([genre['name'] for genre in data.get("genres", [])])
        runtime = data.get("runtime", 0)
        release_date = data.get("release_date", "N/A")
        poster_path = data.get("poster_path")
        
        # NEW: Get the primary spoken language
        spoken_languages = data.get("spoken_languages", [])
        language = spoken_languages[0]['english_name'] if spoken_languages else "N/A"

        # Format runtime
        runtime_formatted = f"{runtime // 60}h {runtime % 60}m" if runtime else "N/A"
            
        # Poster URL
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        # --- Create the new, cleaner caption ---
        caption = (
            f"🎬 *{title}*\n\n"
            f"⭐ *Rating:* {vote_average:.1f} / 10\n"
            f"🎭 *Genre:* {genres}\n"
            f"🌐 *Language:* {language}\n"  # Added language line
            f"🕒 *Runtime:* {runtime_formatted}\n"
            f"📅 *Release Date:* {release_date}"
        )
        
        # --- NEW: Create the Inline Button ---
        tmdb_url = f"https://www.themoviedb.org/movie/{movie_id}"
        keyboard = [
            [
                InlineKeyboardButton("More Info on TMDB", url=tmdb_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # --- Send the final message with the button ---
        if poster_url:
            await update.message.reply_photo(
                photo=poster_url,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=reply_markup  # Add the button here
            )
        else:
            # Also add button for text-only replies
            await update.message.reply_text(
                caption,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await update.message.reply_text("Sorry, I'm having trouble connecting to the movie database.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again later.")


def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY environment variable not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)

    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME environment variable not set!")
        return
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}"
    )

if __name__ == '__main__':
    main()
