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
import html
import math
import random # For random word feature

# --- Library Import Attempts & Flags ---
_initial_logger = logging.getLogger(__name__ + "_initial_check")
if not _initial_logger.hasHandlers():
    _handler = logging.StreamHandler(); _formatter = logging.Formatter('%(asctime)s - Initial %(levelname)s - %(message)s')
    _handler.setFormatter(_formatter); _initial_logger.addHandler(_handler); _initial_logger.setLevel(logging.INFO)

try:
    import eng_to_ipa
    ENG_TO_IPA_AVAILABLE = True
    _initial_logger.info("eng_to_ipa library found.")
except ImportError: ENG_TO_IPA_AVAILABLE = False; _initial_logger.warning("eng_to_ipa not found. Basic clues. `pip install eng_to_ipa`")

try:
    from translate import Translator
    TRANSLATOR_AVAILABLE = True
    _initial_logger.info("'translate' library found.")
except ImportError: TRANSLATOR_AVAILABLE = False; _initial_logger.warning("'translate' not found. Translations disabled. `pip install translate`")

try:
    from openai import AsyncOpenAI
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_API_KEY: openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY); OPENAI_AVAILABLE = True; _initial_logger.info("OpenAI lib and key loaded.")
    else: OPENAI_AVAILABLE = False; _initial_logger.warning("OPENAI_API_KEY env var not set. AI disabled.")
except ImportError: OPENAI_AVAILABLE = False; _initial_logger.warning("OpenAI lib not found. AI disabled. `pip install openai`")

# --- Configuration ---
BOT_TOKEN = "TELEGRAM TOKEN" # YOUR TOKEN

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE": logger.critical("FATAL: Bot token not set!"); exit("Bot token error.")

REMINDER_INTERVALS_SECONDS = [
    60, 1440*60, 2880*60, 5760*60, 11520*60, 17280*60, 23040*60, 28800*60,
    37440*60, 48960*60, 69120*60, 86440*60, 115200*60, 144000*60
]

VOCABULARY_PACK_FILE = "vocabulary_pack_b2plus.txt"
CURATED_VOCABULARY_PACK = []
try:
    with open(VOCABULARY_PACK_FILE, "r") as f:
        CURATED_VOCABULARY_PACK = sorted(list(set([line.strip() for line in f if line.strip()])))
    if CURATED_VOCABULARY_PACK: _initial_logger.info(f"Loaded {len(CURATED_VOCABULARY_PACK)} words from {VOCABULARY_PACK_FILE}.")
    else: _initial_logger.warning(f"{VOCABULARY_PACK_FILE} is empty. Curated pack feature will be limited.")
except FileNotFoundError: _initial_logger.error(f"{VOCABULARY_PACK_FILE} not found! Curated pack feature disabled."); CURATED_VOCABULARY_PACK = []

# --- Callback data prefixes ---
CALLBACK_DELETE_REQUEST = "del_req:"
CALLBACK_DELETE_CONFIRM = "del_conf:"
CALLBACK_DELETE_CANCEL = "del_can:"
CALLBACK_CLUE_REQUEST = "clue_req:"
CALLBACK_AI_EXPLAIN = "ai_explain:"
CALLBACK_SORT_DICT = "sort_dict:"
CALLBACK_DICT_PAGE_NEXT = "dict_pg_n:"
CALLBACK_DICT_PAGE_PREV = "dict_pg_p:"

# --- Reply Keyboard Button Texts ---
LEARNING_DICT_BUTTON_TEXT = "📚 Learning Dictionary"
ADD_CURATED_PACK_BUTTON_TEXT = "➕ Pre-defined Vocabulary Pack (B2+ | 1 USD)"
JULIE_PACK_BUTTON_TEXT = "🎓 Julie Stolyarchuk's Pack"
RANDOM_WORD_BUTTON_TEXT = "🎲 Random Word"
RUN_QUIZ_BUTTON_TEXT = "📝 Run Quiz"

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(LEARNING_DICT_BUTTON_TEXT)],
        [KeyboardButton(ADD_CURATED_PACK_BUTTON_TEXT)],
        [KeyboardButton(JULIE_PACK_BUTTON_TEXT)],
        [KeyboardButton(RANDOM_WORD_BUTTON_TEXT), KeyboardButton(RUN_QUIZ_BUTTON_TEXT)]
    ],
    resize_keyboard=True, input_field_placeholder="Enter word/phrase or select..."
)

# --- Constants for Pack & Dictionary Display ---
USER_PACK_DATA_KEY = "curated_pack_data_v3" # This key will be used in context.user_data
PACK_SCHEDULER_JOB_NAME_PREFIX = "pack_scheduler_"
MAX_PACK_WORDS_PER_DAY = 5
MIN_DELAY_BETWEEN_PACK_WORDS_SECONDS = 3600
WORDS_PER_PAGE = 25


# --- Helper Functions ---
def count_vowels(text: str) -> int:
    return sum(1 for char in text if char in "aeiouAEIOU")

def get_clue_and_translations(word: str) -> str:
    word_cleaned = word.strip().lower(); phonetic_clue_str = "Phonetic Clue: Not available."; translations_str = "\n\nTranslations:\n"
    if not word_cleaned: return "N/A (empty word)"
    if ENG_TO_IPA_AVAILABLE:
        try:
            if not re.fullmatch(r"[a-zA-Z']+",word_cleaned): phonetic_clue_str=f"Basic: {word_cleaned[0]}-{word_cleaned[-1]} V:{count_vowels(word_cleaned)}"
            else: ipa=eng_to_ipa.convert(word_cleaned); phonetic_clue_str = f"IPA: /{ipa}/" if ipa!=word_cleaned and '*' not in ipa else f"Basic: {word_cleaned[0]}-{word_cleaned[-1]} V:{count_vowels(word_cleaned)}"
        except Exception as e: logger.error(f"IPA Err:'{word_cleaned}':{e}"); phonetic_clue_str="Phonetic:Error"
    else: phonetic_clue_str = f"Basic: {word_cleaned[0]}-{word_cleaned[-1]} V:{count_vowels(word_cleaned)}"
    if TRANSLATOR_AVAILABLE:
        langs={'es':'Spanish','fr':'French','de':'German','ru':'Russian'}; found,errs=False,False
        for code,name in langs.items():
            try:
                translator = Translator(to_lang=code, from_lang='en')
                translation_result = translator.translate(word_cleaned)
                if translation_result and translation_result.lower() != word_cleaned:
                    translations_str+=f"- {name}: {html.unescape(translation_result)}\n"; found=True
            except Exception as e: logger.error(f"Trans Err:'{word_cleaned}'-{name}:{e}",exc_info=False);translations_str+=f"- {name}:Error\n";errs=True
        if not found and not errs: translations_str+="No distinct translations."
        elif not found and errs: translations_str+="Translation errors."
    else: translations_str="\n\nTranslations:(Disabled)"
    return f"{phonetic_clue_str}{translations_str}"

async def get_ai_explanation(word_or_phrase:str)->str:
    if not OPENAI_AVAILABLE or not openai_client: return "AI unavailable."
    w=word_or_phrase.strip(); logger.info(f"AI for:'{w}'")
    if not w: return "Empty text."
    try:
        p=f"Explain \"{w}\" simply for ESL. Main meaning & 1 example. Concise. If phrase, explain phrase."
        c=await openai_client.chat.completions.create(messages=[{"role":"system","content":"Helpful ESL assistant."}, {"role":"user","content":p}],model="gpt-3.5-turbo",max_tokens=150,temperature=0.7)
        r=c.choices[0].message.content; return r.strip() if r else "AI no explanation."
    except Exception as e: logger.error(f"OpenAI Err:'{w}':{e}",exc_info=True); return "AI error."

# --- generate_dictionary_text ---
# user_data_for_chat argument will be context.user_data
# chat_specific_settings argument will be context.chat_data
def generate_dictionary_text(
    chat_id: int,
    user_data_for_chat: dict, # This is context.user_data for the specific user
    job_queue: JobQueue,
    page_number: int = 1, items_per_page: int = WORDS_PER_PAGE,
    sort_key_func=None, sort_reverse=False
) -> tuple[str, list, int, int]:
    if not job_queue: return "Cannot access schedule.", [], 1, 1
    now_datetime = datetime.datetime.now()
    display_items_list = []
    processed_active_words = set()
    active_display_map = {}
    for job in job_queue.jobs():
        if job and job.chat_id == chat_id and job.data and 'message_text' in job.data and not job.removed:
            msg_txt = job.data['message_text']
            job_data_item = job.data
            status = 'active_pack' if job_data_item.get('is_pack_word') else 'active_user'
            if msg_txt not in active_display_map:
                active_display_map[msg_txt] = {'reminders_left': 0, 'next_run_dt': job.next_run_time, 'job_data': job_data_item, 'status': status}
            active_display_map[msg_txt]['reminders_left'] += 1
            if job.next_run_time and \
               (active_display_map[msg_txt]['next_run_dt'] is None or \
                job.next_run_time < active_display_map[msg_txt]['next_run_dt']):
                active_display_map[msg_txt]['next_run_dt'] = job.next_run_time
            processed_active_words.add(msg_txt)
    for msg_txt, data in active_display_map.items():
        display_items_list.append((msg_txt, data['reminders_left'], data['next_run_dt'], data['job_data'], data['status'], None))

    # Pack data is stored in user_data_for_chat (context.user_data)
    user_pack_info = user_data_for_chat.get(USER_PACK_DATA_KEY)
    if user_pack_info and 'pack_words_status' in user_pack_info:
        for pack_word_obj in user_pack_info['pack_words_status']:
            word, status, est_start_date = pack_word_obj['word'], pack_word_obj['status'], pack_word_obj.get('estimated_start_date')
            if status == 'pending' and word not in processed_active_words:
                display_items_list.append((word, len(REMINDER_INTERVALS_SECONDS), None,
                                           {'is_pack_word': True, 'learning_start_date': est_start_date, 'message_text':word},
                                           'pending_pack', est_start_date))

    if not display_items_list: return "Dictionary empty. Add words or start a Pack!", [], 1, 1

    if sort_key_func:
        try: display_items_list.sort(key=sort_key_func, reverse=sort_reverse)
        except Exception as e_sort: logger.error(f"Sort error:{e_sort}")

    total_items = len(display_items_list)
    paginated_items = []
    is_all_items_mode = (items_per_page == float('inf')) or \
                        (total_items > 0 and isinstance(items_per_page, (int, float)) and items_per_page >= total_items)

    if is_all_items_mode:
        paginated_items = display_items_list
        current_page_for_display = 1
        total_pages_for_display = 1
    else:
        if total_items == 0:
            current_page_for_display = 1
            total_pages_for_display = 1
        else:
            actual_items_per_page = max(1, int(items_per_page)) if isinstance(items_per_page, (int, float)) and items_per_page != float('inf') else WORDS_PER_PAGE
            total_pages_for_display = math.ceil(total_items / actual_items_per_page)
            current_page_for_display = max(1, min(int(page_number), total_pages_for_display))
            start_index = (current_page_for_display - 1) * actual_items_per_page
            end_index = start_index + actual_items_per_page
            paginated_items = display_items_list[start_index:end_index]

    response_text = f"📚 Your Learning Dictionary (Page {current_page_for_display}/{total_pages_for_display}):\n\n"
    if not paginated_items and total_items > 0:
        response_text += "No items on this page.\n"
    elif not paginated_items and total_items == 0:
        response_text += "Dictionary is currently empty.\n"

    for msg_txt, reminders_left, next_run_dt, job_data_item, item_status, estimated_start_date in paginated_items:
        info_str = "N/A"; is_pack_word = job_data_item.get('is_pack_word', False)
        actual_learning_start_date_str = job_data_item.get('learning_start_date')

        if item_status == 'pending_pack' and estimated_start_date:
            info_str = f"Starts around: {estimated_start_date}"
        elif item_status.startswith('active') and next_run_dt:
            show_actual_learning_start_date = False
            if is_pack_word and actual_learning_start_date_str and REMINDER_INTERVALS_SECONDS:
                try:
                    tz_info = next_run_dt.tzinfo or datetime.timezone.utc
                    learning_start_dt_obj = datetime.datetime.strptime(actual_learning_start_date_str, "%Y-%m-%d").replace(tzinfo=tz_info)
                    expected_first_rem_time = learning_start_dt_obj + datetime.timedelta(seconds=REMINDER_INTERVALS_SECONDS[0])
                    if abs((next_run_dt - expected_first_rem_time).total_seconds()) < 60*10 and next_run_dt > now_datetime.astimezone(tz_info):
                        show_actual_learning_start_date = True; info_str = f"Active since: {actual_learning_start_date_str}"
                except ValueError: logger.error(f"Parse err: {actual_learning_start_date_str} for {msg_txt}")
            if not show_actual_learning_start_date:
                diff = next_run_dt - now_datetime.astimezone(next_run_dt.tzinfo or datetime.timezone.utc)
                if diff.total_seconds() > 0:
                    d = diff.total_seconds() / 86400
                    if d < (1/24): info_str = f"in ~{int(round(d*1440))} min"
                    elif d < 1: info_str = f"in ~{int(round(d*24))} hr(s)"
                    else: info_str = f"in ~{int(round(d))} day(s)"
                else: info_str = "Soon/Past"
        elif item_status.startswith('active'): info_str = "Active (Next N/A)"
        response_text += f"- {msg_txt} (Reminders: {reminders_left}, Status: {info_str})\n"

    response_text += "\nThese are your learning items."
    return response_text, display_items_list, current_page_for_display, total_pages_for_display

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.data or 'message_text' not in job.data: logger.warning(f"Job {job.name or 'N/A'} missing data."); return
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
    except Exception as e: logger.error(f"Err send_reminder job {job.name or 'N/A'}:{e}",exc_info=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! Send an English word/phrase. I'll use Spaced Repetition. Use buttons below for options.",
        reply_markup=REPLY_KEYBOARD )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ai_text = "- **AI Explanations:** '✨ Explain (AI)' for AI insights (if available).\n" if OPENAI_AVAILABLE else ""
    curated_pack_text = f"- **`{ADD_CURATED_PACK_BUTTON_TEXT}`:** Gradually adds a B2+ word list (max {MAX_PACK_WORDS_PER_DAY}/day).\n"
    julie_pack_help_text = f"- **`{JULIE_PACK_BUTTON_TEXT}`:** (Coming Soon!) Another special vocabulary pack.\n"
    random_quiz_text = (
        f"- **`{RANDOM_WORD_BUTTON_TEXT}`:** Get a random word from your active learning list.\n"
        f"- **`{RUN_QUIZ_BUTTON_TEXT}`:** (Coming Soon!) Test your knowledge.\n"
    )
    help_text = (
        "Unlock English Vocabulary Growth!\n\n"
        "This bot uses **Spaced Repetition (SRS)** to help you *remember* words. "
        "SRS schedules reminders at increasing intervals for optimal learning.\n\n"
        "**How it works:**\n"
        "1. **Send Word:** Type any English word/phrase.\n"
        "2. **Reminders:** I'll schedule reminders (e.g., 1 min, 1 day, 2 days...). \n"
        "3. **Recall:** Actively recall meaning on reminder.\n\n"
        "**Features:**\n"
        f"- **`{LEARNING_DICT_BUTTON_TEXT}`:** View paginated list of active AND planned words, reminders left, next due/start time (now {WORDS_PER_PAGE} per page).\n"
        f"{curated_pack_text}"
        f"{julie_pack_help_text}"
        f"{random_quiz_text}"
        "- **Delete Words:** '🗑️ Delete' on reminders (for active words).\n"
        "- **Clue & Translate:** '💡 Clue/Translate' for phonetic hint & translations.\n"
        f"{ai_text}"
        "- **Sort Dictionary:** '🔃 Sort (Ease)' button to sort your learning list by a heuristic for pronunciation ease (length, then vowel count).\n"
        "**Tips:** Add words promptly. Keep phrases short.\n\n"
        "Happy learning! 🚀 /start" )
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD, parse_mode='Markdown')

# --- MODIFIED: show_dictionary_command_wrapper ---
# Uses context.chat_data for chat-specific settings like sort order and current page
# Uses context.user_data for user-specific data like curated pack status
async def show_dictionary_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                          page_number: int = 1,
                                          sort_key_func=None,
                                          sort_reverse=False,
                                          sort_type_str="default") -> None:
    chat_id = update.effective_chat.id
    # chat_data is for settings specific to this chat (sort, current page)
    # user_data is for settings specific to the user (pack status, which is user-wide)
    chat_specific_settings = context.chat_data
    user_specific_data = context.user_data # For USER_PACK_DATA_KEY

    if sort_key_func is not None:
        chat_specific_settings['dict_sort_key_name'] = sort_type_str
        chat_specific_settings['dict_sort_reverse'] = sort_reverse
    else:
        saved_sort_type = chat_specific_settings.get('dict_sort_key_name', 'default')
        saved_sort_reverse = chat_specific_settings.get('dict_sort_reverse', False)
        sort_type_str = saved_sort_type
        sort_reverse = saved_sort_reverse
        if saved_sort_type == "ease_asc": sort_key_func = lambda i:(len(i[0]),count_vowels(i[0]))
        elif saved_sort_type == "ease_desc": sort_key_func = lambda i:(len(i[0]),count_vowels(i[0]))
        elif saved_sort_type == "default": sort_key_func = lambda i:(i[0].lower() if isinstance(i[0],str) else i[0])

    dictionary_text, _, current_page_displayed, total_pages = generate_dictionary_text(
        chat_id, user_specific_data, context.job_queue, # Pass user_specific_data for pack info
        page_number=page_number, items_per_page=WORDS_PER_PAGE,
        sort_key_func=sort_key_func, sort_reverse=sort_reverse
    )

    next_sort_type_for_button,button_text = "ease_desc","🔃 Sort (Ease)"
    if sort_type_str == "ease_asc": button_text = "🔃 Sort (Ease ↓)"; next_sort_type_for_button = "ease_desc"
    elif sort_type_str == "ease_desc": button_text = "Sort A-Z (Default)"; next_sort_type_for_button = "default"
    elif sort_type_str == "default": next_sort_type_for_button = "ease_asc"

    inline_keyboard_buttons_row1 = [
        InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_SORT_DICT}{next_sort_type_for_button}")
    ]
    inline_keyboard_buttons_row2 = []
    if current_page_displayed > 1:
        inline_keyboard_buttons_row2.append(InlineKeyboardButton("◀️ Previous", callback_data=f"{CALLBACK_DICT_PAGE_PREV}{current_page_displayed-1}"))
    if current_page_displayed < total_pages:
        inline_keyboard_buttons_row2.append(InlineKeyboardButton("Next ▶️", callback_data=f"{CALLBACK_DICT_PAGE_NEXT}{current_page_displayed+1}"))

    full_inline_keyboard = [inline_keyboard_buttons_row1]
    if inline_keyboard_buttons_row2:
        full_inline_keyboard.append(inline_keyboard_buttons_row2)
    keyboard = InlineKeyboardMarkup(full_inline_keyboard)

    message_to_send = dictionary_text
    if len(dictionary_text) > 4090:
        message_to_send = dictionary_text[:4000] + "\n\n... (Dictionary page too long)"
        logger.warning(f"Paginated dictionary for chat {chat_id} still too long.")

    if update.callback_query:
        try: await update.callback_query.edit_message_text(text=message_to_send, reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Edit dict err (msg_id {update.callback_query.message.message_id}):{e}")
            if "Message is not modified" not in str(e):
                await update.effective_chat.send_message(text=message_to_send,reply_markup=keyboard)
    else:
        await update.message.reply_text(message_to_send,reply_markup=REPLY_KEYBOARD)
        await update.message.reply_text("Dictionary Options:",reply_markup=keyboard)

    chat_specific_settings['dict_current_page'] = current_page_displayed
    logger.info(f"Showed dict chat {chat_id}, page {current_page_displayed}/{total_pages}, sort: {sort_type_str}")
# --- END MODIFIED ---

async def schedule_reminders_for_word(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_message: str,
    original_message_id: int = None, is_pack_word: bool = False
    ):
    logger.info(f"Internal scheduling for: '{user_message}' for chat {chat_id}, pack_word: {is_pack_word}")
    if not context.job_queue: logger.warning(f"No JobQueue for chat {chat_id}."); return False
    active_jobs_for_word = sum(1 for j in context.job_queue.jobs() if
                               j and j.chat_id == chat_id and
                               j.data and j.data.get('message_text') == user_message
                               and not j.removed)
    if active_jobs_for_word > 0:
        logger.info(f"Word '{user_message}' already has {active_jobs_for_word} active reminders. Updating status if pack word.")
        if is_pack_word:
            # Pack status is in context.user_data
            user_data_for_this_user = context.user_data
            if USER_PACK_DATA_KEY in user_data_for_this_user:
                pack_status_list = user_data_for_this_user.get(USER_PACK_DATA_KEY, {}).get('pack_words_status', [])
                for item in pack_status_list:
                    if item.get('word') == user_message and item.get('status') != 'active':
                        item['status'] = 'active'; item['actual_start_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
                        logger.info(f"Updated status for pack word '{user_message}' to 'active'.")
                        break
        return False
    learning_start_date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    job_data = {'message_text': user_message, 'original_message_id': original_message_id,
                'learning_start_date': learning_start_date_str, 'is_pack_word': is_pack_word}
    scheduled_count = 0; safe_msg_base = re.sub(r'\W+','_',user_message)[:20]
    for i, interval_seconds in enumerate(REMINDER_INTERVALS_SECONDS):
        msg_id_part = original_message_id if original_message_id else f"pack_{hash(user_message) & 0xffffffff}"
        job_name = f"rem_{chat_id}_{msg_id_part}_{safe_msg_base}_{i}"
        context.job_queue.run_once(send_reminder, datetime.timedelta(seconds=interval_seconds),
                                   chat_id=chat_id, data=job_data.copy(), name=job_name)
        scheduled_count += 1
    if scheduled_count > 0: logger.info(f"Scheduled {scheduled_count} for '{user_message}'."); return True
    else: logger.warning(f"No reminders scheduled for '{user_message}'."); return False

async def handle_user_message_for_scheduling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id,user_msg,msg_id = update.effective_chat.id,update.message.text.strip(),update.message.message_id
    if not user_msg: logger.info(f"Empty msg from {chat_id}."); return
    logger.info(f"User added: '{user_msg}' from {update.effective_user.username} in {chat_id}")
    success = await schedule_reminders_for_word(context, chat_id, user_msg, original_message_id=msg_id, is_pack_word=False)
    if success:
        first_min = int(REMINDER_INTERVALS_SECONDS[0]/60) if REMINDER_INTERVALS_SECONDS else 0
        first_txt = f"First in ~{first_min} min." if first_min > 0 else "First scheduled."
        await update.message.reply_text(f"✅ Added '{user_msg}'!\n{first_txt} Total {len(REMINDER_INTERVALS_SECONDS)}.", reply_markup=REPLY_KEYBOARD)
    else: await update.message.reply_text(f"ℹ️ '{user_msg}' might already be in dict or error.", reply_markup=REPLY_KEYBOARD)

# --- MODIFIED: process_curated_pack_for_user ---
# Uses context.user_data directly as it's already scoped to the user by the job's chat_id
async def process_curated_pack_for_user(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job; chat_id = job.chat_id
    # user_data_for_chat is context.user_data (already specific to the user for whom the job runs)
    user_data_for_chat = context.user_data
    # No need for application_user_data_store or .get(chat_id) if job's context correctly provides user_data

    if USER_PACK_DATA_KEY not in user_data_for_chat or 'pack_words_status' not in user_data_for_chat[USER_PACK_DATA_KEY]:
        logger.warning(f"Pack scheduler for {chat_id} missing essential pack data in context.user_data. Removing job.");
        job.schedule_removal(); return

    pack_data = user_data_for_chat[USER_PACK_DATA_KEY]
    pack_words_status_list = pack_data.get('pack_words_status', [])
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    if pack_data.get("last_scheduled_date") != today_str:
        pack_data["words_scheduled_today"] = 0; pack_data["last_scheduled_date"] = today_str
    if pack_data.get("words_scheduled_today", 0) >= MAX_PACK_WORDS_PER_DAY: logger.info(f"{chat_id}: Max pack words for today."); return
    current_time = datetime.datetime.now().timestamp()
    if pack_data.get("last_pack_word_scheduled_time", 0.0) > 0.0 and \
       (current_time - pack_data["last_pack_word_scheduled_time"]) < MIN_DELAY_BETWEEN_PACK_WORDS_SECONDS:
        logger.info(f"{chat_id}: Not enough delay since last pack word."); return

    word_to_schedule_info = None
    for word_status_obj in pack_words_status_list:
        if word_status_obj.get('status') == 'pending': word_to_schedule_info = word_status_obj; break
    if not word_to_schedule_info:
        if pack_data.get('status') != 'completed':
            logger.info(f"All curated words processed for {chat_id}. Setting pack to completed.")
            await context.bot.send_message(chat_id, "🎉 All words from the curated pack have now been activated!")
            pack_data['status'] = 'completed'
        job.schedule_removal(); return

    word_to_schedule = word_to_schedule_info['word']
    logger.info(f"{chat_id}: Attempting to activate pack word '{word_to_schedule}'.")
    newly_scheduled_jobs = await schedule_reminders_for_word(context, chat_id, word_to_schedule, is_pack_word=True)
    if newly_scheduled_jobs :
        word_to_schedule_info['status'] = 'active'; word_to_schedule_info['actual_start_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        pack_data["words_scheduled_today"] = pack_data.get("words_scheduled_today", 0) + 1
        pack_data["last_pack_word_scheduled_time"] = current_time
        num_active_or_completed = sum(1 for w in pack_words_status_list if w.get('status') != 'pending' and w.get('status') != 'cancelled_by_user')
        if num_active_or_completed == 1 and pack_data["words_scheduled_today"] == 1:
             await context.bot.send_message(chat_id, f"➕ Started adding '{word_to_schedule}' from curated pack! More soon.")
        elif pack_data["words_scheduled_today"] == 1: # Ensure message is sent only for the first word of the day's batch
             await context.bot.send_message(chat_id, f"🗓️ Activating new pack words today. '{word_to_schedule}' is now active!")
# --- END MODIFIED ---

# --- MODIFIED: add_curated_words_command ---
# Uses context.user_data for pack information
async def add_curated_words_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_data_for_chat = context.user_data # pack data is user-specific

    if not CURATED_VOCABULARY_PACK: await update.message.reply_text("Curated pack unavailable.",reply_markup=REPLY_KEYBOARD); return

    if USER_PACK_DATA_KEY in user_data_for_chat:
        pack_data = user_data_for_chat[USER_PACK_DATA_KEY]
        if pack_data.get('status')=='completed': await update.message.reply_text("You've completed the pack!",reply_markup=REPLY_KEYBOARD); return
        elif pack_data.get('status')=='in_progress' or any(w.get('status')=='pending' for w in pack_data.get('pack_words_status',[])):
             await update.message.reply_text("Pack already being added.",reply_markup=REPLY_KEYBOARD); return

    pack_words_status_list = []
    current_est_date = datetime.date.today(); words_for_curr_date = 0
    for i,word in enumerate(CURATED_VOCABULARY_PACK):
        if words_for_curr_date >= MAX_PACK_WORDS_PER_DAY: current_est_date+=datetime.timedelta(days=1); words_for_curr_date=0
        pack_words_status_list.append({'word':word,'status':'pending','estimated_start_date':current_est_date.strftime("%Y-%m-%d"),'actual_start_date':None})
        words_for_curr_date+=1

    user_data_for_chat[USER_PACK_DATA_KEY] = {"pack_words_status":pack_words_status_list,"words_scheduled_today":0,"last_scheduled_date":"","last_pack_word_scheduled_time":0.0,"status":"in_progress"}
    job_name = f"{PACK_SCHEDULER_JOB_NAME_PREFIX}{chat_id}"
    for job_item in context.job_queue.get_jobs_by_name(job_name): job_item.schedule_removal()
    context.job_queue.run_repeating(process_curated_pack_for_user, interval=MIN_DELAY_BETWEEN_PACK_WORDS_SECONDS/2, first=5, chat_id=chat_id, name=job_name, user_id=update.effective_user.id) # Pass user_id for job context

    total_words, days_intro = len(CURATED_VOCABULARY_PACK), math.ceil(len(CURATED_VOCABULARY_PACK)/MAX_PACK_WORDS_PER_DAY)
    await update.message.reply_text(f"Great! B2+ Pack ({total_words} words) added. Up to {MAX_PACK_WORDS_PER_DAY} daily. ~{days_intro} days for all to activate. Check '📚 Learning Dictionary'!",reply_markup=REPLY_KEYBOARD)
    logger.info(f"Curated pack for user {update.effective_user.id} in chat {chat_id}. Job '{job_name}' on.")

    class MinimalJob: # For initial processing
        def __init__(self,cid, uid):self.chat_id=cid; self.user_id = uid; self.name=f"init_pack_{cid}"
        def schedule_removal(self):pass

    # Create a temporary context with the correct user_data for the initial pack processing
    # This is a bit of a workaround to ensure the correct user_data is used by process_curated_pack_for_user
    # when called directly without a real job context from JobQueue.
    # A more robust solution might involve ensuring process_curated_pack_for_user always gets user_data passed explicitly
    # or that the JobQueue context is always properly set up.
    
    temp_app = Application.builder().token(BOT_TOKEN).build() # Dummy app for context
    temp_job_context = MinimalJob(chat_id, update.effective_user.id)
    
    # Manually prepare user_data for the temporary context.
    # This part is tricky because context.user_data is normally managed by PTB.
    # For direct calls, we need to ensure it's correctly populated.
    # The most straightforward way is to rely on context.user_data from the handler.
    
    temp_ctx = ContextTypes.DEFAULT_TYPE(application=context.application, bot=context.bot, chat_data=context.chat_data.copy(), user_data=context.user_data.copy()) # Pass copies
    temp_ctx.job = temp_job_context


    logger.info(f"Initial processing pack for user {update.effective_user.id} in chat {chat_id}...")
    for _ in range(MAX_PACK_WORDS_PER_DAY+1):
        if USER_PACK_DATA_KEY not in temp_ctx.user_data or temp_ctx.user_data[USER_PACK_DATA_KEY].get('status')=='completed':break
        await process_curated_pack_for_user(temp_ctx) # Pass the temporary context
        # Check user_data from the original context to see if words_scheduled_today was updated
        if context.user_data.get(USER_PACK_DATA_KEY,{}).get("words_scheduled_today",0)>=MAX_PACK_WORDS_PER_DAY:break
    logger.info(f"Initial pack proc for user {update.effective_user.id} in {chat_id} done.")
# --- END MODIFIED ---


# --- MODIFIED: random_word_command ---
# Uses context.user_data for pack information
async def random_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_specific_data = context.user_data # For USER_PACK_DATA_KEY

    _, all_items_list, _, _ = generate_dictionary_text(
        chat_id, user_specific_data, context.job_queue, # Pass user_specific_data
        page_number=1, items_per_page=float('inf')
    )
    active_words = [
        item[0] for item in all_items_list
        if item[4] in ('active_user', 'active_pack')
    ]
    unique_active_words = list(set(active_words))

    if unique_active_words:
        random_word = random.choice(unique_active_words)
        await update.message.reply_text(f"🎲 Your random word: {random_word}\nTry to recall its meaning!", reply_markup=REPLY_KEYBOARD)
        logger.info(f"Sent random word '{random_word}' to chat {chat_id}")
    else:
        await update.message.reply_text("Your active learning dictionary is empty. Add some words first!", reply_markup=REPLY_KEYBOARD)
        logger.info(f"Random word requested for chat {chat_id}, but dictionary is empty.")
# --- END MODIFIED ---

async def run_quiz_placeholder_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} clicked placeholder button: {RUN_QUIZ_BUTTON_TEXT}")
    await update.message.reply_text(
        "📝 The Quiz feature will be available soon! Keep learning!",
        reply_markup=REPLY_KEYBOARD
    )

async def julie_pack_placeholder_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id; logger.info(f"User {chat_id} clicked: {JULIE_PACK_BUTTON_TEXT}")
    await update.message.reply_text("🌟 Julie Stolyarchuk's Pack coming soon!",reply_markup=REPLY_KEYBOARD)

# --- MODIFIED: button_callback_handler ---
# Uses context.chat_data for chat-specific settings
# Uses context.user_data for user-specific data (pack status)
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer(); callback_data = query.data; chat_id = query.message.chat_id
    logger.info(f"Callback from chat {chat_id}: {callback_data}")

    chat_specific_settings = context.chat_data
    user_specific_data = context.user_data

    try:
        if callback_data.startswith(CALLBACK_DELETE_REQUEST):
            word = callback_data[len(CALLBACK_DELETE_REQUEST):]; cb_confirm, cb_cancel = f"{CALLBACK_DELETE_CONFIRM}{word}", f"{CALLBACK_DELETE_CANCEL}{word}"
            if len(cb_confirm.encode()) > 64 or len(cb_cancel.encode()) > 64: await query.edit_message_text(f"{query.message.text}\n\n⚠️ Word too long for confirm.", reply_markup=None); return
            kbd = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes",callback_data=cb_confirm), InlineKeyboardButton("❌ No",callback_data=cb_cancel)]])
            await query.edit_message_text(f"❓ Remove \"{word}\"?\n(Original: {query.message.text})", reply_markup=kbd)
        elif callback_data.startswith(CALLBACK_DELETE_CONFIRM):
            word_to_delete = callback_data[len(CALLBACK_DELETE_CONFIRM):]
            if not context.job_queue: await query.edit_message_text("❌ Error: No schedule access.",reply_markup=None); return
            word_updated_in_pack = False
            # Pack data is in user_specific_data (context.user_data)
            if USER_PACK_DATA_KEY in user_specific_data and 'pack_words_status' in user_specific_data[USER_PACK_DATA_KEY]:
                for pack_word_obj in user_specific_data[USER_PACK_DATA_KEY]['pack_words_status']:
                    if pack_word_obj['word'] == word_to_delete: pack_word_obj['status'] = 'cancelled_by_user'; word_updated_in_pack = True; break
            removed_jobs = sum(1 for j in list(context.job_queue.jobs()) if j and j.chat_id==chat_id and j.data and j.data.get('message_text')==word_to_delete and not j.removed and (j.schedule_removal() or True))
            response_msg = f"✅ \"{word_to_delete}\" "; response_msg += f"({removed_jobs} reminders) removed." if removed_jobs > 0 else ("removed from pack plan." if word_updated_in_pack else "not found active/planned.")
            if word_updated_in_pack and removed_jobs > 0 : response_msg += " Also updated in pack."
            await query.edit_message_text(response_msg, reply_markup=None)
        elif callback_data.startswith(CALLBACK_DELETE_CANCEL):
            word = callback_data[len(CALLBACK_DELETE_CANCEL):]; orig_txt_match = re.search(r"\(Original: (.*)\)", query.message.text,re.DOTALL); orig_txt = orig_txt_match.group(1).strip() if orig_txt_match else f"🔔 Reminder: {word}"
            await query.edit_message_text(f"{orig_txt}\n\n❌ Deletion cancelled.", reply_markup=None)
        elif callback_data.startswith(CALLBACK_CLUE_REQUEST):
            word = callback_data[len(CALLBACK_CLUE_REQUEST):]; logger.info(f"Clue/Translate for '{word}'"); info_txt = get_clue_and_translations(word)
            await context.bot.send_message(chat_id=chat_id, text=f"💡 Info for \"{word}\":\n{info_txt}", reply_to_message_id=query.message.message_id)
        elif callback_data.startswith(CALLBACK_AI_EXPLAIN):
            word_to_explain = callback_data[len(CALLBACK_AI_EXPLAIN):]; logger.info(f"AI Explanation for '{word_to_explain}'"); await context.bot.send_chat_action(chat_id=chat_id, action="typing"); ai_explanation_text = await get_ai_explanation(word_to_explain)
            await context.bot.send_message(chat_id=chat_id, text=f"✨ AI for \"{word_to_explain}\":\n\n{ai_explanation_text}", reply_to_message_id=query.message.message_id, parse_mode='Markdown' )
        elif callback_data.startswith(CALLBACK_SORT_DICT):
            sort_type_requested = callback_data[len(CALLBACK_SORT_DICT):]; logger.info(f"Sort dict type: {sort_type_requested}")
            sort_key_to_apply,reverse_sort_to_apply = None,False
            if sort_type_requested=="ease_asc": sort_key_to_apply=lambda item:(len(item[0]),count_vowels(item[0])); reverse_sort_to_apply=False
            elif sort_type_requested=="ease_desc": sort_key_to_apply=lambda item:(len(item[0]),count_vowels(item[0])); reverse_sort_to_apply=True
            elif sort_type_requested=="default": sort_key_to_apply=lambda item:item[0].lower(); reverse_sort_to_apply=False
            else: logger.warning(f"Unrec sort type '{sort_type_requested}'"); sort_key_to_apply=lambda item:item[0].lower(); reverse_sort_to_apply=False; sort_type_requested="default"
            await show_dictionary_command_wrapper(update, context, page_number=1, sort_key_func=sort_key_to_apply, sort_reverse=reverse_sort_to_apply, sort_type_str=sort_type_requested)
        elif callback_data.startswith(CALLBACK_DICT_PAGE_NEXT) or callback_data.startswith(CALLBACK_DICT_PAGE_PREV):
            # current_page_from_data = chat_specific_settings.get('dict_current_page', 1) # Not strictly needed if page comes from callback
            if callback_data.startswith(CALLBACK_DICT_PAGE_NEXT):
                requested_page = int(callback_data[len(CALLBACK_DICT_PAGE_NEXT):])
            else: # PREV
                requested_page = int(callback_data[len(CALLBACK_DICT_PAGE_PREV):])
            logger.info(f"Dictionary pagination requested. Requested page: {requested_page}")
            await show_dictionary_command_wrapper(update, context, page_number=requested_page)
        else: await query.edit_message_text("😕 Unknown action.", reply_markup=None)
    except Exception as e:
        logger.error(f"Error in button_callback_handler for callback data '{callback_data}': {e}", exc_info=True)
        try: await query.edit_message_text("😕 An error occurred.", reply_markup=None)
        except Exception as inner_e: logger.error(f"Could not edit msg on error: {inner_e}")
# --- END MODIFIED ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

def main() -> None:
    logger.info(f"Starting bot. Token: {BOT_TOKEN[:8]}...{BOT_TOKEN[-4:] if len(BOT_TOKEN)>12 else ''}")
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        lambda u,c: show_dictionary_command_wrapper(u,c,page_number=1, sort_key_func=lambda i_tuple:(i_tuple[0].lower() if isinstance(i_tuple[0], str) else i_tuple[0]),sort_reverse=False,sort_type_str="default")
    ))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(ADD_CURATED_PACK_BUTTON_TEXT)}$'), add_curated_words_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(JULIE_PACK_BUTTON_TEXT)}$'), julie_pack_placeholder_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(RANDOM_WORD_BUTTON_TEXT)}$'), random_word_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(RUN_QUIZ_BUTTON_TEXT)}$'), run_quiz_placeholder_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND &
        ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$') &
        ~filters.Regex(f'^{re.escape(ADD_CURATED_PACK_BUTTON_TEXT)}$') &
        ~filters.Regex(f'^{re.escape(JULIE_PACK_BUTTON_TEXT)}$') &
        ~filters.Regex(f'^{re.escape(RANDOM_WORD_BUTTON_TEXT)}$') &
        ~filters.Regex(f'^{re.escape(RUN_QUIZ_BUTTON_TEXT)}$'),
        handle_user_message_for_scheduling))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    application.add_error_handler(error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot stopped.")

if __name__ == '__main__':
    if not logging.getLogger(__name__ + "_initial_check").hasHandlers():
         _h=logging.StreamHandler();_f=logging.Formatter('%(asctime)s-Initial %(levelname)s-%(message)s');_h.setFormatter(_f)
         _il=logging.getLogger(__name__+"_initial_check");_il.addHandler(_h);_il.setLevel(logging.INFO)
    main()
