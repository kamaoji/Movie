# bot.py (Version 8 - Strict Language Filtering)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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

# --- Language and Region Mapping (Unchanged) ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'},
    'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'},
    'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'},
    'fr': {'name': 'French', 'region': 'FR'},
}

# --- Button Keyboard Helpers (Unchanged) ---
def get_main_menu_keyboard():
    keyboard = [[InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hi'), InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')], [InlineKeyboardButton("More Languages 🌍", callback_data='show_more_langs')]]
    return InlineKeyboardMarkup(keyboard)

def get_more_languages_keyboard():
    keyboard = [[InlineKeyboardButton("Tamil", callback_data='lang_ta'), InlineKeyboardButton("Telugu", callback_data='lang_te')], [InlineKeyboardButton("Spanish", callback_data='lang_es'), InlineKeyboardButton("French", callback_data='lang_fr')], [InlineKeyboardButton("« Back", callback_data='back_to_main')]]
    return InlineKeyboardMarkup(keyboard)

# --- Start and Button Handlers (Unchanged) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = f"Hey {user.first_name}! 👋 Welcome to the Ultimate Movie Bot! 🎬\n\nReady to find your next favorite film?\n\nChoose your preferred language below to get tailored results! 👇"
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'show_more_langs':
        await query.edit_message_text(text="Here are some more popular languages:", reply_markup=get_more_languages_keyboard())
    elif data == 'back_to_main':
        await query.edit_message_text(text="Choose your preferred language or send me a title directly!", reply_markup=get_main_menu_keyboard())
    elif data.startswith('lang_'):
        lang_code = data.split('_')[1]
        context.user_data['language'] = lang_code
        lang_name = LANGUAGE_DATA.get(lang_code, {}).get('name', 'selected language')
        await query.edit_message_text(text=f"✅ Great! Your preferred language is set to *{lang_name}*.\n\nNow, send me any movie title to search!", parse_mode='Markdown')

# --- MODIFIED: search_tmdb now STRICTLY filters by language ---
async def search_tmdb(query: str, region: str | None = None, lang_code: str | None = None) -> dict | None:
    logger.info(f"Searching TMDB for: '{query}' with region: {region} and language filter: {lang_code}")
    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
        if region:
            search_url += f"®ion={region}"

        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()
        if not search_data.get("results"):
            return None

        # --- THIS IS THE NEW STRICT FILTERING LOGIC ---
        found_movie_id = None
        if lang_code:
            logger.info(f"Strictly filtering search results for language: {lang_code}")
            for movie in search_data["results"]:
                # The search result gives the original language of the movie
                if movie.get('original_language') == lang_code:
                    found_movie_id = movie['id']
                    logger.info(f"Found language-matched movie: {movie.get('title')} (ID: {found_movie_id})")
                    break  # Stop searching once we find the first match
        else:
            # If no language is set, just take the top result as before
            found_movie_id = search_data["results"][0]["id"]

        # If after filtering, we have no movie ID, it means no match was found.
        if not found_movie_id:
            logger.info("No movie found matching the strict language criteria.")
            return None
        # --- END OF NEW LOGIC ---

        details_url = f"https://api.themoviedb.org/3/movie/{found_movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()

        return {
            "source": "TMDB", "title": data.get("title", "N/A"),
            "rating": f"{data.get('vote_average', 0):.1f} / 10",
            "genre": ", ".join([g['name'] for g in data.get("genres", [])]),
            "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A",
            "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A",
            "release_date": data.get("release_date", "N/A"),
            "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,
            "button_url": f"https://www.themoviedb.org/movie/{found_movie_id}"
        }
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None

# --- Main orchestrator function ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    user_lang_code = context.user_data.get('language')
    region = LANGUAGE_DATA.get(user_lang_code, {}).get('region') if user_lang_code else None

    # Pass the language code to the search function for strict filtering
    media_data = await search_tmdb(query, region=region, lang_code=user_lang_code)
    
    # If TMDB fails (including our new language filter), fall back to OMDb
    if not media_data:
        media_data = await search_omdb(query)
        
    if not media_data:
        # This message now correctly shows if the movie is not found in the chosen language
        await update.message.reply_text("Movie not found in the selected language or any of my databases.")
        return
        
    caption = (
        f"🎬 *{media_data['title']}*\n\n"
        f"⭐ *{media_data['source']} Rating:* {media_data['rating']}\n"
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
        await update.message.reply_photo(photo=media_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)

# --- Unchanged OMDb search and error handler ---
async def search_omdb(query: str) -> dict | None:
    logger.info(f"Falling back to OMDb for: {query}")
    # This function remains a general, non-filtered search
    try:
        api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={query}"
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        if data.get("Response") != "True": return None
        return {
            "source": "IMDb", "title": data.get("Title", "N/A"),
            "rating": f"{data.get('imdbRating', 'N/A')} / 10",
            "genre": data.get("Genre", "N/A"), "language": data.get("Language", "N/A"),
            "runtime": data.get("Runtime", "N/A"), "release_date": data.get("Released", "N/A"),
            "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else None,
            "button_url": f"https://www.imdb.com/title/{data.get('imdbID')}" if data.get('imdbID') else None
        }
    except Exception as e:
        logger.error(f"OMDb search failed: {e}")
        return None

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# --- Unchanged main function ---
def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, OMDB_API_KEY]):
        logger.error("One or more API keys are missing from environment variables!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)

    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME environment variable not set!")
        return
    
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN, webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}")

if __name__ == '__main__':
    main()
