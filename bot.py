# bot.py (Version 4.2: Corrected Filter Instance Usage)

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, UpdateType
from telegram.error import BadRequest, Forbidden

# --- Configuration from Environment Variables ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL")
DB_CHANNEL_ID = os.environ.get("DB_CHANNEL_ID")
WELCOME_IMAGE_FILE_ID = os.environ.get("WELCOME_IMAGE_FILE_ID")

# --- In-Memory Database ---
file_db = {}

# --- Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Bot Logic ---

# 1. Force Subscribe and Membership Check
async def check_user_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user: return False
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATES_CHANNEL, user_id=user.id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except (BadRequest, Forbidden):
        logger.error(f"Error checking membership for {user.id} in {UPDATES_CHANNEL}. Is bot an admin?")
        return False

async def force_subscribe_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, handler_func):
    # Determine the message object to reply to
    message_to_reply = update.message or (update.callback_query.message if update.callback_query else None)
    if not message_to_reply: return
    
    if await check_user_membership(update, context):
        await handler_func(update, context)
    else:
        channel_link = f"https://t.me/{UPDATES_CHANNEL.lstrip('@')}"
        keyboard = [[InlineKeyboardButton("📢 JOIN CHANNEL 📢", url=channel_link)], [InlineKeyboardButton("🔄 Try Again 🔄", callback_data="check_join")]]
        await message_to_reply.reply_text("❗*Please join our Updates Channel to use this bot\\.*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)

# 2. File Indexing (Listens to the Database Channel)
async def file_indexer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if not message: return

    file = message.document or message.video or message.audio
    if file:
        file_name = file.file_name
        file_id = file.file_id
        file_db[file_name] = file_id
        logger.info(f"Indexed file: {file_name} with ID: {file_id}")
        try:
            await message.reply_text(f"✅ Indexed: `{file_name}`", parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.warning(f"Could not reply in DB channel: {e}")

# 3. User-Facing Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await force_subscribe_wrapper(update, context, start_action)

async def start_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message or update.callback_query.message
    keyboard = [[InlineKeyboardButton("🔍 Search Files 🔍", callback_data="search_prompt")]]
    await message.reply_photo(
        photo=WELCOME_IMAGE_FILE_ID,
        caption=f"Hey {user.first_name}\\!\n\nWelcome to the File Search Bot\\. Use the button or just send me a name to search for\\.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await force_subscribe_wrapper(update, context, search_action)

async def search_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.lower()
    results = {name: fid for name, fid in file_db.items() if query in name.lower()}
    
    if not results:
        await update.message.reply_text("😞 No files found matching your query.")
        return

    context.user_data['search_results'] = list(results.items())
    context.user_data['search_query'] = query
    await display_search_results(update, context, page=0)

async def display_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    results = context.user_data.get('search_results', [])
    query = context.user_data.get('search_query', 'your query')
    items_per_page = 5
    start_index = page * items_per_page
    end_index = start_index + items_per_page
    page_items = results[start_index:end_index]
    
    keyboard = []
    for name, file_id in page_items:
        keyboard.append([InlineKeyboardButton(f"🎬 {name[:40]}", callback_data=f"sendfile_{file_id}")])

    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"page_{page-1}"))
    if end_index < len(results): nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page+1}"))
    if nav_row: keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"Found *{len(results)}* files for '_{query.replace('.', '\\.')}_':"
    
    effective_message = update.callback_query.message if update.callback_query else update.message
    try:
        await effective_message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
             await effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            if update.callback_query: await update.callback_query.answer()

# 4. Button and Callback Handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_join":
        await force_subscribe_wrapper(query, context, start_action)
    elif data == "search_prompt":
        await query.message.reply_text("Please send the name of the file you want to find.")
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        await display_search_results(update, context, page=page)
    elif data.startswith("sendfile_"):
        file_id = data.split("_", 1)[1]
        await context.bot.send_document(chat_id=query.from_user.id, document=file_id, caption="Here is your file!")

# --- Main Application Setup ---
def main() -> None:
    if not all([TELEGRAM_TOKEN, UPDATES_CHANNEL, DB_CHANNEL_ID, WELCOME_IMAGE_FILE_ID]):
        logger.fatal("FATAL: One or more required environment variables are missing.")
        return

    allowed_updates = [UpdateType.MESSAGE, UpdateType.CALLBACK_QUERY, UpdateType.CHANNEL_POST]
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # THE FIX IS HERE: Using all-caps filter instances
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=int(DB_CHANNEL_ID)) & (filters.DOCUMENT | filters.VIDEO | filters.AUDIO), 
        file_indexer
    ))
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    PORT = int(os.environ.get('PORT', 8443))
    WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')
    
    logger.info("Starting bot...")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}",
        allowed_updates=allowed_updates
    )

if __name__ == '__main__':
    main()
