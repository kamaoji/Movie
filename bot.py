# bot.py (Version 9 - Smart Fallback with Language Check)

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- Configuration & Logging (Unchanged) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Language and Button Data (Unchanged) ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'}, 'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'}, 'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'}, 'fr': {'name': 'French', 'region': 'FR'},
}

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

# --- search_tmdb (Unchanged) ---
async def search_tmdb(query: str, region: str | None = None, lang_code: str | None = None) -> dict | None:
    logger.info(f"Searching TMDB for: '{query}' with region: {region} and language filter: {lang_code}")
    try:
        headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_API_KEY}"}
        search_url = f"https://api.themoviedb.org/3/search/movie?query={query}&include_adult=false&language=en-US&page=1"
        if region: search_url += f"®ion={region}"
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_data = response.json()
        if not search_data.get("results"): return None
        found_movie_id = None
        if lang_code:
            for movie in search_data["results"]:
                if movie.get('original_language') == lang_code:
                    found_movie_id = movie['id']
                    break
        else:
            found_movie_id = search_data["results"][0]["id"]
        if not found_movie_id: return None
        details_url = f"https://api.themoviedb.org/3/movie/{found_movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()
        return {"source": "TMDB", "title": data.get("title", "N/A"), "rating": f"{data.get('vote_average', 0):.1f} / 10", "genre": ", ".join([g['name'] for g in data.get("genres", [])]), "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A", "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A", "release_date": data.get("release_date", "N/A"), "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "button_url": f"https://www.themoviedb.org/movie/{found_movie_id}"}
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None

# --- MODIFIED: search_omdb now also checks the language ---
async def search_omdb(query: str, lang_name: str | None = None) -> dict | None:
    logger.info(f"Falling back to OMDb for: '{query}' with language preference: {lang_name}")
    try:
        api_url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={query}"
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        if data.get("Response") != "True": return None

        # --- THIS IS THE NEW BUG FIX ---
        if lang_name:
            # OMDb can return multiple languages like "English, Hindi"
            omdb_languages = data.get("Language", "").split(", ")
            if lang_name not in omdb_languages:
                logger.info(f"OMDb found a movie, but it's not in the preferred language ({lang_name}). Found: {omdb_languages}")
                return None # Reject the movie if it's the wrong language
        # --- END OF BUG FIX ---

        return {"source": "IMDb", "title": data.get("Title", "N/A"), "rating": f"{data.get('imdbRating', 'N/A')} / 10", "genre": data.get("Genre", "N/A"), "language": data.get("Language", "N/A"), "runtime": data.get("Runtime", "N/A"), "release_date": data.get("Released", "N/A"), "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else None, "button_url": f"https://www.imdb.com/title/{data.get('imdbID')}" if data.get('imdbID') else None}
    except Exception as e:
        logger.error(f"OMDb search failed: {e}")
        return None

# --- Main orchestrator function (Now passes lang_name to OMDb) ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    user_lang_code = context.user_data.get('language')
    region = LANGUAGE_DATA.get(user_lang_code, {}).get('region') if user_lang_code else None
    # NEW: Get the full language name for our new OMDb check
    lang_name_for_omdb = LANGUAGE_DATA.get(user_lang_code, {}).get('name') if user_lang_code else None

    media_data = await search_tmdb(query, region=region, lang_code=user_lang_code)
    
    if not media_data:
        # Pass the language name to the OMDb search
        media_data = await search_omdb(query, lang_name=lang_name_for_omdb)
        
    if not media_data:
        await update.message.reply_text("Movie not found in the selected language or any of my databases.")
        return
        
    caption = (f"🎬 *{media_data['title']}*\n\n"
               f"⭐ *{media_data['source']} Rating:* {media_data['rating']}\n"
               f"🎭 *Genre:* {media_data['genre']}\n"
               f"🌐 *Language:* {media_data['language']}\n"
               f"🕒 *Runtime:* {media_data['runtime']}\n"
               f"📅 *Release Date:* {media_data['release_date']}")
    
    reply_markup = None
    if media_data.get('button_url'):
        button_text = f"More Info on {media_data['source']}"
        keyboard = [[InlineKeyboardButton(button_text, url=media_data['button_url'])]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    if media_data.get('poster_url'):
        await update.message.reply_photo(photo=media_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)

# --- Unchanged error handler and main function ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

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
