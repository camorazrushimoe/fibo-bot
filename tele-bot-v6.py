import os
import logging
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
    CallbackQueryHandler
)
import re
import html # For unescaping HTML entities

# --- Library Import Attempts & Flags ---
# Configure a basic logger for import attempts before the main logger is set up
_initial_logger = logging.getLogger(__name__ + "_initial_check")
if not _initial_logger.hasHandlers(): # Avoid adding multiple handlers if script is re-run in some envs
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter('%(asctime)s - Initial %(levelname)s - %(message)s')
    _handler.setFormatter(_formatter)
    _initial_logger.addHandler(_handler)
    _initial_logger.setLevel(logging.INFO)

try:
    import eng_to_ipa
    ENG_TO_IPA_AVAILABLE = True
    _initial_logger.info("eng_to_ipa library found.")
except ImportError:
    ENG_TO_IPA_AVAILABLE = False
    _initial_logger.warning("eng_to_ipa not found. Phonetic clues will be basic. To enable, run: pip install eng_to_ipa")

try:
    from translate import Translator
    TRANSLATOR_AVAILABLE = True
    _initial_logger.info("'translate' library found.")
except ImportError:
    TRANSLATOR_AVAILABLE = False
    _initial_logger.warning("'translate' library not found. Translation feature disabled. To enable, run: pip install translate")

try:
    from openai import AsyncOpenAI
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        OPENAI_AVAILABLE = True
        _initial_logger.info("OpenAI library found and API key loaded.")
    else:
        OPENAI_AVAILABLE = False
        _initial_logger.warning("OPENAI_API_KEY environment variable not set. AI features disabled.")
except ImportError:
    OPENAI_AVAILABLE = False
    _initial_logger.warning("OpenAI library not found. AI features disabled. To enable, run: pip install openai")

# --- Configuration ---
# IMPORTANT: For production, consider moving BOT_TOKEN to an environment variable.
BOT_TOKEN = "place for TG token" # YOUR PROVIDED TOKEN

# Configure main logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    force=True # Force reconfig if initial basicConfig was called by library import checks
)
logger = logging.getLogger(__name__) # Main logger for the script

# Basic check if using a placeholder, though you've provided a real one
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE": 
    logger.critical("FATAL: Bot token is not set in the script or is still the placeholder value! Please update BOT_TOKEN.")
    exit("Bot token not configured.")

REMINDER_INTERVALS_SECONDS = [
    60,         # 1 minute
    1440 * 60,  # 1 day
    2880 * 60,  # 2 days
    5760 * 60,  # 4 days
    11520 * 60, # 8 days
    17280 * 60, # 12 days
    23040 * 60, # 16 days
    28800 * 60, # 20 days
    37440 * 60, # 26 days
    48960 * 60, # 34 days
    69120 * 60, # 48 days
    86440 * 60, # 60 days
    115200 * 60,# 80 days
    144000 * 60 # 100 days
]

# Callback data prefixes
CALLBACK_DELETE_REQUEST = "del_req:"
CALLBACK_DELETE_CONFIRM = "del_conf:"
CALLBACK_DELETE_CANCEL = "del_can:"
CALLBACK_CLUE_REQUEST = "clue_req:"
CALLBACK_AI_EXPLAIN = "ai_explain:"
CALLBACK_SORT_DICT = "sort_dict:" 

LEARNING_DICT_BUTTON_TEXT = "📚 Learning Dictionary"
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(LEARNING_DICT_BUTTON_TEXT)]],
    resize_keyboard=True,
    input_field_placeholder="Enter word/phrase or select..."
)


# --- Helper Functions ---
def count_vowels(text: str) -> int:
    """Counts the number of vowels in a given text string."""
    vowels = "aeiouAEIOU" # Consider both cases
    return sum(1 for char in text if char in vowels)

def get_clue_and_translations(word: str) -> str:
    word_cleaned = word.strip().lower()
    if not word_cleaned: return "N/A (empty word)"

    # --- Phonetic Clue Part ---
    phonetic_clue_str = "Phonetic Clue: Not available."
    if ENG_TO_IPA_AVAILABLE:
        try:
            if not re.fullmatch(r"[a-zA-Z']+", word_cleaned): # Allows letters and apostrophes
                first_l_ph, last_l_ph = (word_cleaned[0], word_cleaned[-1]) if word_cleaned else ('?', '?')
                phonetic_clue_str = f"Basic: Starts '{first_l_ph}', ends '{last_l_ph}'. Vowels: {count_vowels(word_cleaned)}."
            else:
                ipa_transcription = eng_to_ipa.convert(word_cleaned)
                if ipa_transcription == word_cleaned or '*' in ipa_transcription:
                    first_l_ph2, last_l_ph2 = (word_cleaned[0], word_cleaned[-1]) if word_cleaned else ('?', '?')
                    phonetic_clue_str = f"Basic: Starts '{first_l_ph2}', ends '{last_l_ph2}'. Vowels: {count_vowels(word_cleaned)}."
                else:
                    phonetic_clue_str = f"IPA: /{ipa_transcription}/"
        except Exception as e_ipa:
            logger.error(f"Error getting IPA for '{word_cleaned}': {e_ipa}")
            phonetic_clue_str = "Phonetic Clue: Error generating."
    else: # Basic clue if eng_to_ipa not available
        first_l_basic, last_l_basic = (word_cleaned[0], word_cleaned[-1]) if word_cleaned else ('?', '?')
        phonetic_clue_str = f"Basic: Starts '{first_l_basic}', ends '{last_l_basic}'. Vowels: {count_vowels(word_cleaned)}."

    # --- Translation Part ---
    translations_str = "\n\nTranslations:\n"
    if TRANSLATOR_AVAILABLE:
        target_languages = {
            'es': 'Spanish', 'fr': 'French', 'de': 'German', 'ru': 'Russian',
        }
        translations_found, any_errors = False, False
        for lang_code, lang_name in target_languages.items():
            try:
                translator = Translator(to_lang=lang_code, from_lang='en')
                translation_result = translator.translate(word_cleaned)
                if translation_result and translation_result.lower() != word_cleaned:
                    translation_result = html.unescape(translation_result)
                    translations_str += f"- {lang_name}: {translation_result}\n"
                    translations_found = True
            except Exception as e_trans:
                logger.error(f"Error translating '{word_cleaned}' to {lang_name}: {e_trans}", exc_info=False)
                translations_str += f"- {lang_name}: Error\n"
                any_errors = True
        
        if not translations_found and not any_errors:
             translations_str += "Could not retrieve distinct translations or word is similar in these languages."
        elif not translations_found and any_errors: # If only errors occurred
            translations_str += "Could not retrieve translations due to errors with the translation service."
    else:
        translations_str = "\n\nTranslations: (Feature disabled - 'translate' library not installed/found)"
    return f"{phonetic_clue_str}{translations_str}"

async def get_ai_explanation(word_or_phrase: str) -> str:
    if not OPENAI_AVAILABLE or not openai_client:
        return "AI explanation feature is currently unavailable."
    word_to_explain = word_or_phrase.strip()
    if not word_to_explain:
        return "Cannot explain an empty word/phrase."
    logger.info(f"Requesting AI explanation for: '{word_to_explain}'")
    try:
        prompt_message = (
            f"You are a helpful assistant for English language learners. "
            f"Explain the word or short phrase \"{word_to_explain}\" in simple terms. "
            f"Provide its primary meaning and one clear example sentence using it. "
            f"Keep the explanation concise and easy to understand. If it's a phrase, explain the phrase."
        )
        chat_completion = await openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant for English language learners."},
                {"role": "user", "content": prompt_message}
            ],
            model="gpt-3.5-turbo", max_tokens=150, temperature=0.7,
        )
        response_content = chat_completion.choices[0].message.content
        if response_content:
            return response_content.strip()
        else:
            return "AI could not provide an explanation for this word/phrase."
    except Exception as e:
        logger.error(f"Error calling OpenAI API for '{word_to_explain}': {e}", exc_info=True)
        return "Sorry, there was an error getting an AI explanation."

def generate_dictionary_text(chat_id: int, job_queue: JobQueue, sort_key_func=None, sort_reverse=False) -> tuple[str, list]:
    if not job_queue:
        return "Sorry, I cannot access the reminder schedule right now.", []

    current_jobs = job_queue.jobs()
    now = datetime.datetime.now()
    active_word_jobs = {}
    for job in current_jobs:
        if job and job.chat_id == chat_id and job.data and 'message_text' in job.data and not job.removed:
            active_word_jobs.setdefault(job.data['message_text'], []).append(job)

    if not active_word_jobs:
        return "Your learning dictionary is currently empty.", []

    display_items = []
    for msg_txt, jobs in active_word_jobs.items():
        reminders_left = len(jobs)
        next_run = min((j.next_run_time for j in jobs if j.next_run_time), default=None)
        display_items.append((msg_txt, reminders_left, next_run))
    
    if sort_key_func:
        try:
            display_items.sort(key=sort_key_func, reverse=sort_reverse)
        except Exception as e_sort:
            logger.error(f"Error during dictionary sort: {e_sort}")

    response_text = "📚 Your Learning Dictionary:\n\n"
    for msg_txt, reminders_left, next_run in display_items:
        next_info = "N/A"
        if next_run:
            current_time_for_comparison = now.astimezone(next_run.tzinfo) if next_run.tzinfo else now
            diff = next_run - current_time_for_comparison
            if diff.total_seconds() > 0:
                d = diff.total_seconds() / 86400 # days
                if d < (1/24): next_info = f"in ~{int(round(d*1440))} min"
                elif d < 1: next_info = f"in ~{int(round(d*24))} hr(s)"
                else: next_info = f"in ~{int(round(d))} day(s)"
            else: next_info = "Soon/Past"
        response_text += f"- {msg_txt} (Left: {reminders_left}, Next: {next_info})\n"
    
    response_text += "\nThese are the items you are currently learning."
    return response_text, [item[0] for item in display_items]


# --- Telegram Bot Handlers ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.data or 'message_text' not in job.data:
         logger.warning(f"Job {job.name or 'N/A'} missing data."); return
    try:
        msg_txt, chat_id = job.data['message_text'], job.chat_id
        buttons = []
        cb_del = f"{CALLBACK_DELETE_REQUEST}{msg_txt}"
        if len(cb_del.encode()) <= 64: buttons.append(InlineKeyboardButton("🗑️ Delete", callback_data=cb_del))
        
        word_clue_ai = msg_txt.split(' ')[0] if ' ' in msg_txt else msg_txt
        word_clue_ai_clean = re.sub(r'[^\w\s\'-]', '', word_clue_ai).strip()
        if word_clue_ai_clean:
            cb_clue = f"{CALLBACK_CLUE_REQUEST}{word_clue_ai_clean}"
            if len(cb_clue.encode()) <= 64: buttons.append(InlineKeyboardButton("💡 Clue/Translate", callback_data=cb_clue))
            if OPENAI_AVAILABLE:
                cb_ai = f"{CALLBACK_AI_EXPLAIN}{word_clue_ai_clean}"
                if len(cb_ai.encode()) <= 64: buttons.append(InlineKeyboardButton("✨ Explain (AI)", callback_data=cb_ai))
        
        kbd = InlineKeyboardMarkup([buttons]) if buttons else None
        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Reminder: {msg_txt}", reply_markup=kbd)
        logger.info(f"Sent reminder '{msg_txt}' to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending reminder for job {job.name or 'N/A'}: {e}", exc_info=True)
        try:
            if job and job.chat_id: await context.bot.send_message(chat_id=job.chat_id, text="Error sending reminder.")
        except Exception as e_notify: logger.error(f"Could not notify user on failed reminder: {e_notify}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! Send an English word/phrase. I'll use Spaced Repetition. Use '{LEARNING_DICT_BUTTON_TEXT}' to see your list.",
        reply_markup=REPLY_KEYBOARD )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ai_text = "- **AI Explanations:** '✨ Explain (AI)' for AI insights (if available).\n" if OPENAI_AVAILABLE else ""
    help_text = (
        "Unlock English Vocabulary Growth!\n\n"
        "This bot uses **Spaced Repetition (SRS)** to help you *remember* words. "
        "SRS schedules reminders at increasing intervals for optimal learning.\n\n"
        "**How it works:**\n"
        "1. **Send Word:** Type any English word/phrase.\n"
        "2. **Reminders:** I'll schedule reminders (e.g., 1 min, 1 day, 2 days...). \n"
        "3. **Recall:** Actively recall meaning on reminder.\n\n"
        "**Features:**\n"
        f"- **`{LEARNING_DICT_BUTTON_TEXT}`:** View list, reminders left, next due.\n"
        "- **Delete Words:** '🗑️ Delete' on reminders.\n"
        "- **Clue & Translate:** '💡 Clue/Translate' for phonetic hint & translations.\n"
        f"{ai_text}"
        "- **Sort Dictionary:** '🔃 Sort (Ease)' button to sort your learning list by a heuristic for pronunciation ease (length, then vowel count).\n"
        "**Tips:** Add words promptly. Keep phrases short.\n\n"
        "Happy learning! 🚀 /start" )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD, parse_mode='Markdown')
    logger.info(f"Sent help to {update.effective_user.username}")

async def show_dictionary_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                sort_key_func=None, sort_reverse=False, sort_type_str="default") -> None:
    chat_id = update.effective_chat.id
    
    dictionary_text, _ = generate_dictionary_text(chat_id, context.job_queue, sort_key_func, sort_reverse)
    
    next_sort_type_for_button = "ease_desc" # Default next action for "Sort (Ease)"
    button_text = "🔃 Sort (Ease)"
    if sort_type_str == "ease_asc": 
        button_text = "🔃 Sort (Ease ↓)" 
        next_sort_type_for_button = "ease_desc"
    elif sort_type_str == "ease_desc": 
        button_text = "Sort A-Z (Default)" 
        next_sort_type_for_button = "default"
    elif sort_type_str == "default":
        next_sort_type_for_button = "ease_asc"


    buttons = [
        InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_SORT_DICT}{next_sort_type_for_button}")
    ]
    keyboard = InlineKeyboardMarkup([buttons])
    
    if update.callback_query: 
        try:
            await update.callback_query.edit_message_text(text=dictionary_text, reply_markup=keyboard)
        except Exception as e_edit: 
            logger.warning(f"Could not edit dictionary message (id: {update.callback_query.message.message_id}): {e_edit}. Sending new one.")
            await update.effective_chat.send_message(text=dictionary_text, reply_markup=keyboard)
    else: 
        await update.message.reply_text(dictionary_text, reply_markup=REPLY_KEYBOARD) 
        await update.message.reply_text("Additional options:", reply_markup=keyboard)

    logger.info(f"Displayed dictionary for chat {chat_id}, sort: {sort_type_str}")

async def schedule_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id, user_msg, msg_id = update.effective_chat.id, update.message.text.strip(), update.message.message_id
    if not user_msg: 
        logger.info(f"Received empty message from chat {chat_id}. Ignoring.")
        return
    
    logger.info(f"Scheduling: '{user_msg}' from {update.effective_user.username} in chat {chat_id}")
    
    if not context.job_queue:
        logger.warning(f"JobQueue not found for chat {chat_id}. Reminders cannot be scheduled.")
        await update.message.reply_text("Sorry, I cannot schedule reminders right now.", reply_markup=REPLY_KEYBOARD)
        return
    
    existing_job_count = sum(1 for j in context.job_queue.jobs() if j and j.chat_id==chat_id and j.data and j.data.get('message_text')==user_msg and not j.removed)
    if existing_job_count > 0:
        logger.info(f"Message '{user_msg}' already has {existing_job_count} pending reminders for chat {chat_id}.")
        await update.message.reply_text(f"ℹ️ '{user_msg}' is already in your learning dictionary with {existing_job_count} reminders pending.", reply_markup=REPLY_KEYBOARD)
        return
    
    job_data = {'message_text': user_msg, 'original_message_id': msg_id}
    scheduled_count = 0
    first_interval_minutes = None
    
    # --- CORRECTED PART ---
    safe_msg_base = re.sub(r'\W+','_',user_msg)[:20] 
    # --- END CORRECTED PART ---

    for i, interval_seconds in enumerate(REMINDER_INTERVALS_SECONDS):
        # --- CORRECTED PART ---
        job_name = f"rem_{chat_id}_{msg_id}_{safe_msg_base}_{i}" 
        # --- END CORRECTED PART ---
        
        context.job_queue.run_once(
            send_reminder, 
            datetime.timedelta(seconds=interval_seconds), 
            chat_id=chat_id, 
            data=job_data.copy(), 
            name=job_name
        )
        scheduled_count += 1
        if scheduled_count == 1: 
            first_interval_minutes = int(interval_seconds / 60)
        logger.info(f"Scheduled job '{job_name}' for chat {chat_id} to run in {interval_seconds} seconds.")
    
    if scheduled_count > 0:
        first_reminder_text = f"First reminder in approximately {first_interval_minutes} minutes." if first_interval_minutes is not None else "First reminder scheduled."
        await update.message.reply_text(f"✅ Added '{user_msg}' to your learning dictionary!\n{first_reminder_text} Total {scheduled_count} reminders scheduled.", reply_markup=REPLY_KEYBOARD)
    else: 
        logger.warning(f"No jobs were scheduled for '{user_msg}' in chat {chat_id}, although scheduling was attempted.") # Should not happen
        await update.message.reply_text("Couldn't schedule any reminders for some reason. Please try again.", reply_markup=REPLY_KEYBOARD)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    chat_id = query.message.chat_id
    logger.info(f"Callback from chat {chat_id}: {callback_data}")

    try:
        if callback_data.startswith(CALLBACK_DELETE_REQUEST):
            word = callback_data[len(CALLBACK_DELETE_REQUEST):]
            cb_confirm, cb_cancel = f"{CALLBACK_DELETE_CONFIRM}{word}", f"{CALLBACK_DELETE_CANCEL}{word}"
            if len(cb_confirm.encode()) > 64 or len(cb_cancel.encode()) > 64:
                await query.edit_message_text(f"{query.message.text}\n\n⚠️ Word too long for confirm.", reply_markup=None); return
            kbd = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes",callback_data=cb_confirm), InlineKeyboardButton("❌ No",callback_data=cb_cancel)]])
            await query.edit_message_text(f"❓ Remove \"{word}\"?\n(Original: {query.message.text})", reply_markup=kbd)

        elif callback_data.startswith(CALLBACK_DELETE_CONFIRM):
            word = callback_data[len(CALLBACK_DELETE_CONFIRM):]
            if not context.job_queue: await query.edit_message_text("❌ Error: No schedule access.",reply_markup=None); return
            removed = sum(1 for j in list(context.job_queue.jobs()) if j and j.chat_id==chat_id and j.data and j.data.get('message_text')==word and not j.removed and (j.schedule_removal() or True))
            await query.edit_message_text(f"✅ Removed \"{word}\" ({removed} reminders)." if removed > 0 else f"⚠️ No active reminders for \"{word}\".", reply_markup=None)

        elif callback_data.startswith(CALLBACK_DELETE_CANCEL):
            word = callback_data[len(CALLBACK_DELETE_CANCEL):]
            orig_txt_match = re.search(r"\(Original: (.*)\)", query.message.text, re.DOTALL)
            orig_txt = orig_txt_match.group(1).strip() if orig_txt_match else f"🔔 Reminder: {word}"
            await query.edit_message_text(f"{orig_txt}\n\n❌ Deletion cancelled.", reply_markup=None)

        elif callback_data.startswith(CALLBACK_CLUE_REQUEST):
            word = callback_data[len(CALLBACK_CLUE_REQUEST):]
            logger.info(f"Clue/Translate for '{word}'")
            info_txt = get_clue_and_translations(word)
            await context.bot.send_message(chat_id=chat_id, text=f"💡 Info for \"{word}\":\n{info_txt}", reply_to_message_id=query.message.message_id)
        
        elif callback_data.startswith(CALLBACK_AI_EXPLAIN):
            word_to_explain = callback_data[len(CALLBACK_AI_EXPLAIN):]
            logger.info(f"AI Explanation requested for '{word_to_explain}'")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            ai_explanation_text = await get_ai_explanation(word_to_explain)
            await context.bot.send_message(
                chat_id=chat_id, text=f"✨ AI for \"{word_to_explain}\":\n\n{ai_explanation_text}",
                reply_to_message_id=query.message.message_id, parse_mode='Markdown' )
        
        elif callback_data.startswith(CALLBACK_SORT_DICT):
            sort_type_requested = callback_data[len(CALLBACK_SORT_DICT):] 
            logger.info(f"Sort dictionary requested with type: {sort_type_requested}")

            sort_key_to_apply = None
            reverse_sort_to_apply = False
            
            if sort_type_requested == "ease_asc":
                sort_key_to_apply = lambda item: (len(item[0]), count_vowels(item[0])) 
                reverse_sort_to_apply = False
            elif sort_type_requested == "ease_desc":
                sort_key_to_apply = lambda item: (len(item[0]), count_vowels(item[0]))
                reverse_sort_to_apply = True
            elif sort_type_requested == "default": 
                sort_key_to_apply = lambda item: item[0].lower() 
                reverse_sort_to_apply = False
            else: 
                logger.warning(f"Unrecognized sort type '{sort_type_requested}', defaulting to A-Z.")
                sort_key_to_apply = lambda item: item[0].lower()
                reverse_sort_to_apply = False
                sort_type_requested = "default" 
            
            await show_dictionary_command(update, context, sort_key_func=sort_key_to_apply, sort_reverse=reverse_sort_to_apply, sort_type_str=sort_type_requested)
        
        else: await query.edit_message_text("😕 Unknown action.", reply_markup=None)
    except Exception as e:
        logger.error(f"Error in button_callback_handler '{callback_data}': {e}", exc_info=True)
        try: await query.edit_message_text("😕 Error processing action.", reply_markup=None)
        except: pass 

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

def main() -> None:
    logger.info(f"Starting bot. Token: {BOT_TOKEN[:8]}...{BOT_TOKEN[-4:] if len(BOT_TOKEN)>12 else ''}")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'), 
        lambda u, c: show_dictionary_command(u, c, sort_key_func=lambda item: item[0].lower(), sort_reverse=False, sort_type_str="default")
    ))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'), schedule_reminders))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_error_handler(error_handler)
    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot stopped.")

if __name__ == '__main__':
    # This initial basicConfig is for library import checks before main logger is set
    # It helps see warnings if libraries are missing, even if the main logger config later overrides it.
    if not logging.getLogger(__name__ + "_initial_check").hasHandlers(): # Check again to be super safe
         _handler = logging.StreamHandler()
         _formatter = logging.Formatter('%(asctime)s - Initial %(levelname)s - %(message)s')
         _handler.setFormatter(_formatter)
         _initial_logger_main_guard = logging.getLogger(__name__ + "_initial_check")
         _initial_logger_main_guard.addHandler(_handler)
         _initial_logger_main_guard.setLevel(logging.INFO)
    main()
