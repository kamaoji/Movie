# bot.py (Version 5.1 - Language Fix)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- MODIFIED: search_tmdb function with language fix ---
async def search_tmdb(query: str) -> dict | None:
    """Searches TMDB and returns a dictionary of movie data, or None if not found."""
    logger.info(f"Searching TMDB for: {query}")
    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        
        # --- THE FIX IS HERE ---
        # We REMOVED '&language=en-US' from this search URL to make it find more international movies.
        search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&page=1"
        
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()

        if not search_data.get("results"):
            return None

        movie_id = search_data["results"][0]["id"]
        
        # We KEEP '&language=en-US' here so the details (like genre) are in English.
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()

        return {
            "source": "TMDB",
            "title": data.get("title", "N/A"),
            "rating": f"{data.get('vote_average', 0):.1f} / 10",
            "genre": ", ".join([g['name'] for g in data.get("genres", [])]),
            "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A",
            "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A",
            "release_date": data.get("release_date", "N/A"),
            "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,
            "button_url": f"https://www.themoviedb.org/movie/{movie_id}"
        }
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None


# --- OMDb function remains unchanged ---
async def search_omdb(query: str) -> dict | None:
    """Searches OMDb and returns a dictionary of movie data, or None if not found."""
    logger.info(f"Falling back to OMDb for: {query}")
    try:
        api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={query}"
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        if data.get("Response") != "True":
            return None

        return {
            "source": "OMDb",
            "title": data.get("Title", "N/A"),
            "rating": data.get("imdbRating", "N/A"),
            "genre": data.get("Genre", "N/A"),
            "language": data.get("Language", "N/A"),
            "runtime": data.get("Runtime", "N/A"),
            "release_date": data.get("Released", "N/A"),
            "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else None,
            "button_url": f"https://www.imdb.com/title/{data.get('imdbID')}" if data.get('imdbID') else None
        }
    except Exception as e:
        logger.error(f"OMDb search failed: {e}")
        return None


# --- Orchestrator function remains unchanged ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    
    media_data = await search_tmdb(query)
    
    if not media_data:
        media_data = await search_omdb(query)
        
    if not media_data:
        await update.message.reply_text("😞 Sorry, I couldn't find that movie on any of my databases.")
        return
        
    caption = (
        f"🎬 *{media_data['title']}*\n\n"
        f"⭐ *Rating:* {media_data['rating']}\n"
        f"🎭 *Genre:* {media_data['genre']}\n"
        f"🌐 *Language:* {media_data['language']}\n"
        f"🕒 *Runtime:* {media_data['runtime']}\n"
        f"📅 *Release Date:* {media_data['release_date']}"
    )
    
    reply_markup = None
    if media_data.get('button_url'):
        button_text = f"More Info on {media_data['source']}"
        keyboard = [[InlineKeyboardButton(button_text, url=media_data['button_url'])]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    if media_data.get('poster_url'):
        await update.message.reply_photo(
            photo=media_data['poster_url'],
            caption=caption,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            caption,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

# --- Start and error handlers remain unchanged ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Hi {user.first_name}! 🍿\n\nI search multiple databases to find movie info for you. Just send me a title!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)


# --- Main function remains unchanged ---
def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, OMDB_API_KEY]):
        logger.error("One or more API keys are missing from environment variables!")
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
