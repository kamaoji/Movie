# bot.py (Version 10 - Private Channel as a Database)

import os
import logging
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- Configuration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID") # The ID of your private channel

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- In-Memory Index ---
# This dictionary will store our movie index.
# Format: {"title_lang": message_id} e.g., {"baaghi_hi": 123}
movie_index = {}

# --- Language and Button Data (Unchanged) ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'}, 'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'}, 'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'}, 'fr': {'name': 'French', 'region': 'FR'},
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
    welcome_message = f"Hey {user.first_name}! 👋 Welcome to the Ultimate Movie Bot! 🎬\n\nI can now search my own private library for you!\n\nChoose your preferred language below to get tailored results! 👇"
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

# --- NEW: Function to listen to the private channel and update the index ---
async def update_index(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # We only care about messages from our specific private channel
    if str(update.channel_post.chat.id) != PRIVATE_CHANNEL_ID:
        return

    caption = update.channel_post.caption
    if not caption:
        return

    # Use regex to find our hashtags
    title_match = re.search(r'#Title\s+(.+?)(?=\s+#|$)', caption, re.IGNORECASE)
    lang_match = re.search(r'#Lang\s+([a-zA-Z]{2})', caption, re.IGNORECASE)

    if title_match and lang_match:
        title = title_match.group(1).strip().lower()
        lang = lang_match.group(1).strip().lower()
        message_id = update.channel_post.message_id

        # Create a unique key for our index
        index_key = f"{title}_{lang}"
        movie_index[index_key] = message_id
        
        logger.info(f"Indexed movie: Key='{index_key}', Message ID='{message_id}'")
        # Optional: React to the post in the channel to show it was indexed
        await context.bot.add_reaction(chat_id=PRIVATE_CHANNEL_ID, message_id=message_id, reaction="👍")


# --- MODIFIED: The main search function now uses the index as a fallback ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.lower().strip() # Use lowercase for consistent searching
    user_id = update.effective_user.id
    user_lang_code = context.user_data.get('language')

    # --- Step 1: Try TMDB first ---
    region = LANGUAGE_DATA.get(user_lang_code, {}).get('region') if user_lang_code else None
    tmdb_data = await search_tmdb(query, region=region, lang_code=user_lang_code)

    if tmdb_data:
        # If found on TMDB, send the TMDB info
        caption = (f"🎬 *{tmdb_data['title']}*\n\n"
                   f"⭐ *{tmdb_data['source']} Rating:* {tmdb_data['rating']}\n"
                   f"🎭 *Genre:* {tmdb_data['genre']}\n"
                   f"🌐 *Language:* {tmdb_data['language']}\n"
                   f"🕒 *Runtime:* {tmdb_data['runtime']}\n"
                   f"📅 *Release Date:* {tmdb_data['release_date']}")
        
        reply_markup = None
        if tmdb_data.get('button_url'):
            keyboard = [[InlineKeyboardButton(f"More Info on {tmdb_data['source']}", url=tmdb_data['button_url'])]]
            reply_markup = InlineKeyboardMarkup(keyboard)

        if tmdb_data.get('poster_url'):
            await update.message.reply_photo(photo=tmdb_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)
        return

    # --- Step 2: If TMDB fails, search our private channel index ---
    if user_lang_code:
        index_key = f"{query}_{user_lang_code}"
        message_id_to_forward = movie_index.get(index_key)

        if message_id_to_forward:
            logger.info(f"Found movie in private index! Key: '{index_key}', Forwarding message ID: {message_id_to_forward}")
            try:
                await context.bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=PRIVATE_CHANNEL_ID,
                    message_id=message_id_to_forward
                )
                return # Success!
            except Exception as e:
                logger.error(f"Failed to forward message: {e}")
                await update.message.reply_text("I found the movie in my library, but couldn't forward it. Please check my admin permissions in the channel.")
                return

    # --- Step 3: If both fail, send the final error message ---
    await update.message.reply_text("Movie not found in TMDB or my private library for the selected language.")


# --- search_tmdb function (Unchanged) ---
async def search_tmdb(query: str, region: str | None = None, lang_code: str | None = None) -> dict | None:
    # This function is unchanged from the previous version.
    # It performs the strict language search on TMDB.
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
                    found_movie_id = movie['id']; break
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

# --- Error Handler (Unchanged) ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# --- MODIFIED: main function now includes the channel post handler ---
def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, PRIVATE_CHANNEL_ID]):
        logger.error("One or more required environment variables are missing!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    # NEW: This handler listens for new posts in channels your bot is in
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, update_index))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_media))
    application.add_error_handler(error_handler)

    # Webhook setup is unchanged
    PORT = int(os.environ.get('PORT', 8443))
    APP_NAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not APP_NAME:
        logger.error("RENDER_EXTERNAL_HOSTNAME environment variable not set!")
        return
    
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TELEGRAM_TOKEN, webhook_url=f"https://{APP_NAME}/{TELEGRAM_TOKEN}")

if __name__ == '__main__':
    main()
