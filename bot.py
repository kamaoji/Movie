# bot.py (Version 20 - Final, Warning-Free Version)

import os
import logging
import requests
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, PicklePersistence
)

# --- Configuration & Logging ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID")
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Language and Button Data ---
LANGUAGE_DATA = {
    'en': {'name': 'English', 'region': 'US'}, 'hi': {'name': 'Hindi', 'region': 'IN'},
    'ta': {'name': 'Tamil', 'region': 'IN'}, 'te': {'name': 'Telugu', 'region': 'IN'},
    'es': {'name': 'Spanish', 'region': 'ES'}, 'fr': {'name': 'French', 'region': 'FR'},
}

# --- Keyboard Helpers ---
def get_main_menu_keyboard():
    keyboard = [[InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hi'), InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')], [InlineKeyboardButton("More Languages 🌍", callback_data='show_more_langs')]]
    return InlineKeyboardMarkup(keyboard)

def get_more_languages_keyboard():
    keyboard = [[InlineKeyboardButton("Tamil", callback_data='lang_ta'), InlineKeyboardButton("Telugu", callback_data='lang_te')], [InlineKeyboardButton("Spanish", callback_data='lang_es'), InlineKeyboardButton("French", callback_data='lang_fr')], [InlineKeyboardButton("« Back", callback_data='back_to_main')]]
    return InlineKeyboardMarkup(keyboard)

# --- Deletion function ---
async def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, bot_message_id: int, user_message_id: int, user_name: str, delay: int = 60):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_id)
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        logger.info(f"Auto-deleted messages in chat {chat_id}.")
        confirmation_text = f"Hey {user_name},\n\nYour previous request has been deleted to avoid clutter. 👍"
        await context.bot.send_message(chat_id=chat_id, text=confirmation_text)
    except Exception as e:
        logger.warning(f"Could not delete one or both messages in chat {chat_id}: {e}")

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    welcome_message = f"Hey {user.first_name}! 👋 Welcome to the Ultimate Movie Bot! 🎬\n\nMy responses & your requests will be deleted after 1 minute!\n\nChoose your preferred language below. 👇"
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'show_more_langs': await query.edit_message_text(text="Here are some more popular languages:", reply_markup=get_more_languages_keyboard())
    elif data == 'back_to_main': await query.edit_message_text(text="Choose your preferred language or send me a title directly!", reply_markup=get_main_menu_keyboard())
    elif data.startswith('lang_'):
        lang_code = data.split('_')[1]
        context.user_data['language'] = lang_code
        lang_name = LANGUAGE_DATA.get(lang_code, {}).get('name', 'selected language')
        await query.edit_message_text(text=f"✅ Great! Your preferred language is now permanently set to *{lang_name}*.\n\nSend me any movie title to search!", parse_mode='Markdown')

# --- MODIFIED: Indexing function with reaction code removed ---
async def update_index(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.channel_post or str(update.channel_post.chat.id) != PRIVATE_CHANNEL_ID: return
    post = update.channel_post
    caption = post.caption if post.caption else post.text
    if not caption: return
    title_match, lang_match = re.search(r'#Title\s+([^\n]+)', caption, re.IGNORECASE), re.search(r'#Lang\s+([a-zA-Z]{2})', caption, re.IGNORECASE)
    if title_match and lang_match:
        title, lang = title_match.group(1).strip().lower(), lang_match.group(1).strip().lower()
        index_key = f"{title}_{lang}"
        file_id, file_type = (None, None)
        if post.photo: file_id, file_type = post.photo[-1].file_id, "photo"
        elif post.video: file_id, file_type = post.video.file_id, "video"
        elif post.document: file_id, file_type = post.document.file_id, "document"
        elif post.text: file_type = "text"
        context.bot_data.setdefault('movie_index', {})[index_key] = {"file_id": file_id, "file_type": file_type, "original_caption": caption}
        logger.info(f"Persistently Indexed: Key='{index_key}', Type='{file_type}'")
        # The reaction code that caused the warning has been removed.

# --- Helper for URL buttons ---
def create_url_buttons_from_caption(caption: str) -> (str, InlineKeyboardMarkup | None):
    lines, buttons, cleaned_lines = caption.split('\n'), [], []
    url_regex = r'https?://[^\s]+'
    for i, line in enumerate(lines):
        if re.search(url_regex, line):
            if i > 0 and not re.search(url_regex, lines[i-1]):
                button_label = lines[i-1].strip()
                for url in re.findall(url_regex, line): buttons.append([InlineKeyboardButton(button_label, url=url)])
        elif i + 1 < len(lines) and re.search(url_regex, lines[i+1]): pass
        else: cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip(), InlineKeyboardMarkup(buttons) if buttons else None

# --- Main search function ---
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_message_id = update.message.message_id
    query = update.message.text.lower().strip()
    user_lang_code = context.user_data.get('language')
    deletion_warning = "\n\n\n*⚠️ This message & your request will automatically delete in 1 minute!*"
    sent_message = None

    region = LANGUAGE_DATA.get(user_lang_code, {}).get('region') if user_lang_code else None
    tmdb_data = await search_tmdb(query, region=region, lang_code=user_lang_code)
    if tmdb_data:
        caption = (f"🎬 *{tmdb_data['title']}*\n\n⭐ *TMDB Rating:* {tmdb_data['rating']}\n🎭 *Genre:* {tmdb_data['genre']}\n🌐 *Language:* {tmdb_data['language']}\n🕒 *Runtime:* {tmdb_data['runtime']}\n📅 *Release Date:* {tmdb_data['release_date']}") + deletion_warning
        reply_markup = None
        if tmdb_data.get('button_url'): reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"More Info on {tmdb_data['source']}", url=tmdb_data['button_url'])]])
        if tmdb_data.get('poster_url'): sent_message = await update.message.reply_photo(photo=tmdb_data['poster_url'], caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        else: sent_message = await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        if user_lang_code:
            index_key = f"{query}_{user_lang_code}"
            movie_data = context.bot_data.get('movie_index', {}).get(index_key)
            if movie_data:
                final_caption, reply_markup = create_url_buttons_from_caption('\n'.join([line for line in movie_data["original_caption"].split('\n') if '#Title' not in line and '#Lang' not in line]).strip())
                final_caption += deletion_warning
                try:
                    if movie_data["file_type"] == "photo": sent_message = await context.bot.send_photo(chat_id=user.id, photo=movie_data["file_id"], caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                    elif movie_data["file_type"] == "video": sent_message = await context.bot.send_video(chat_id=user.id, video=movie_data["file_id"], caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                    elif movie_data["file_type"] == "document": sent_message = await context.bot.send_document(chat_id=user.id, document=movie_data["file_id"], caption=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                    else: sent_message = await context.bot.send_message(chat_id=user.id, text=final_caption, parse_mode='Markdown', reply_markup=reply_markup)
                except Exception as e:
                    logger.error(f"Failed to re-send message from index: {e}"); await update.message.reply_text("I found the movie in my library, but couldn't send it.")

    if sent_message:
        asyncio.create_task(schedule_message_deletion(context, sent_message.chat_id, sent_message.message_id, user_message_id, user.first_name))
    elif not tmdb_data:
        await update.message.reply_text("Movie not found in TMDB or my private library for the selected language.")

# --- search_tmdb function ---
async def search_tmdb(query: str, region: str | None = None, lang_code: str | None = None) -> dict | None:
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
        else: found_movie_id = search_data["results"][0]["id"]
        if not found_movie_id: return None
        details_url = f"https://api.themoviedb.org/3/movie/{found_movie_id}?language=en-US"
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        data = details_response.json()
        return {"source": "TMDB", "title": data.get("title", "N/A"), "rating": f"{data.get('vote_average', 0):.1f} / 10", "genre": ", ".join([g['name'] for g in data.get("genres", [])]), "language": data.get("spoken_languages")[0]['english_name'] if data.get("spoken_languages") else "N/A", "runtime": f"{data.get('runtime', 0) // 60}h {data.get('runtime', 0) % 60}m" if data.get('runtime') else "N/A", "release_date": data.get("release_date", "N/A"), "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, "button_url": f"https://www.themoviedb.org/movie/{found_movie_id}"}
    except Exception as e:
        logger.error(f"TMDB search failed: {e}")
        return None

# --- Error Handler ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# --- Main function ---
def main() -> None:
    if not all([TELEGRAM_TOKEN, TMDB_API_KEY, PRIVATE_CHANNEL_ID]):
        logger.error("One or more required environment variables are missing!")
        return
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    application = (Application.builder().token(TELEGRAM_TOKEN).persistence(persistence).build())
    if 'movie_index' not in application.bot_data:
        application.bot_data['movie_index'] = {}
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, update_index))
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
