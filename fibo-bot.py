# Add near the top of your script
import os
import logging
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton # <-- Import ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
    # CallbackQueryHandler is no longer needed for this button
)
import re # Needed for Regex filter

## CTRL + C to stop
## sudo systemctl restart telegram-bot.service


# --- Configuration ---
# IMPORTANT: Read token from environment variable

## PRODUCTION PART
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN environment variable set!") # Or log and exit
## END PRODUCTION PART

REMINDER_INTERVALS_SECONDS = [
    # Shortened for easier testing - uncomment the long ones later
    60,         # 1 minute
    # 1440 * 60,      # 1 day
    # ... (rest of your intervals)
    1440 * 60,      # 1 day
    2880 * 60,      # 2 days
    5760 * 60,      # 4 days
    11520 * 60,     # 8 days
    17280 * 60,     # 12 days
    23040 * 60,     # 16 days
    28800 * 60,     # 20 days
    37440 * 60,     # 26 days
    48960 * 60,     # 34 days
    69120 * 60,     # 48 days
    86440 * 60,     # 60 days
    115200 * 60,    # 80 days
    144000 * 60     # 100 days
]
# --- End Configuration ---

# --- Define the persistent keyboard ---
LEARNING_DICT_BUTTON_TEXT = "📚 Learning Dictionary"
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(LEARNING_DICT_BUTTON_TEXT)]], # One row, one button
    resize_keyboard=True,  # Make the button fit nicely
    # one_time_keyboard=False is the default, meaning it persists
    input_field_placeholder="Enter word/phrase or select an option..." # Optional placeholder
)
# --- End Keyboard Definition ---


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Callback function for the scheduled job ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the reminder message back to the user."""
    job = context.job
    if not job or not job.data or 'message_text' not in job.data:
         logger.warning(f"Job {job.name if job else 'N/A'} is missing data or message_text.")
         return

    try:
        message_text = job.data['message_text']
        chat_id = job.chat_id
        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Reminder: {message_text}")
        logger.info(f"Sent reminder '{message_text}' to chat_id {chat_id}")
        # --- Rescheduling logic placeholder (as before) ---

    except KeyError:
        logger.error(f"KeyError accessing data for job {job.name if job else 'N/A'}. Data: {job.data if job else 'N/A'}", exc_info=True)
    except Exception as e:
        logger.error(f"Error sending reminder for job {job.name if job else 'N/A'}: {e}", exc_info=True)
        try:
            if job and job.chat_id:
                 await context.bot.send_message(chat_id=job.chat_id, text="Sorry, I encountered an error sending one of your reminders.")
        except Exception:
            logger.error(f"Could not notify user {job.chat_id if job else 'N/A'} about the failed reminder.")


# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and shows the persistent keyboard."""
    user = update.effective_user
    welcome_text = (
        rf"Hi {user.mention_html()}! Send me a message (word or short phrase) "
        "and I'll remind you about it using spaced repetition.\n\n"
        "Try to send 2-3 words per message for best results.\n\n"
        f"Use the '{LEARNING_DICT_BUTTON_TEXT}' button below to see what's scheduled."
    )

    # Send the welcome message WITH the persistent ReplyKeyboardMarkup
    await update.message.reply_html(
        welcome_text,
        reply_markup=REPLY_KEYBOARD # Use the persistent keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message and ensures the keyboard is visible."""
    intervals_days = [round(s / (60 * 60 * 24), 1) for s in REMINDER_INTERVALS_SECONDS]
    help_text = (
        "I help you learn using spaced repetition.\n\n"
        "➡️ Send me any text message (a word, a phrase).\n"
        "➡️ I will schedule reminders for it.\n"
        f"➡️ Reminders will arrive approximately after: {', '.join(map(str, intervals_days))} days.\n\n"
        "Commands:\n"
        "/start - Show welcome message.\n"
        "/help - Show this help message.\n\n"
        f"Button:\n'{LEARNING_DICT_BUTTON_TEXT}' - View your scheduled items.\n\n"
        "Tip: Keep messages short (2-3 words)!"
    )
    # Also send the keyboard with the help message
    await update.message.reply_text(help_text, reply_markup=REPLY_KEYBOARD)

# --- NEW: Handler for the Reply Keyboard Button Press ---

async def show_dictionary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Learning Dictionary' button press (which sends a text message)."""
    chat_id = update.effective_chat.id
    user_reminders = {}  # Use a dictionary to store messages and their remaining reminders

    if not context.job_queue:
        logger.warning(f"JobQueue not found in context for chat {chat_id} during dictionary fetch.")
        # Send reply ensuring keyboard remains
        await update.message.reply_text(
            "Sorry, I cannot access the reminder schedule right now.",
            reply_markup=REPLY_KEYBOARD
        )
        return

    current_jobs = context.job_queue.jobs()
    logger.info(f"Found {len(current_jobs)} total jobs. Filtering for chat_id {chat_id}.")

    for job in current_jobs:
        if job.chat_id == chat_id and job.data and 'message_text' in job.data:
            try:
                message_text = job.data['message_text']
                if message_text not in user_reminders:
                    user_reminders[message_text] = 0
                user_reminders[message_text] += 1  # Count the remaining reminders for this message
            except Exception as e:
                logger.error(f"Unexpected error processing job {job.name}. Data: {job.data}. Error: {e}", exc_info=True)

    if not user_reminders:
        response_text = "Your learning dictionary is currently empty. Send me a message to start learning!"
    else:
        response_text = "📚 Your Learning Dictionary:\n\n"
        for message, reminders_left in sorted(user_reminders.items()):
            response_text += f"- {message} (Reminders left: {reminders_left})\n"
        response_text += "\nThese are the items you are currently learning."

    # Send the dictionary as a new message, also ensuring the keyboard stays
    await update.message.reply_text(response_text, reply_markup=REPLY_KEYBOARD)
    logger.info(f"Displayed dictionary for chat_id {chat_id}. Items: {len(user_reminders)}")

# --- Message Handler ---

async def schedule_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Schedules reminders for the user's message (ignores the dictionary button text)."""
    # This function is now triggered by ANY text message *except* commands
    # and *except* the specific dictionary button text (handled separately).
    chat_id = update.effective_chat.id
    user_message = update.message.text
    message_id = update.message.message_id
    logger.info(f"Received message id {message_id} from {update.effective_user.username} in chat {chat_id} for scheduling: {user_message}")

    if not context.job_queue:
        logger.warning(f"JobQueue not found in context for chat {chat_id}. Reminders cannot be scheduled.")
        await update.message.reply_text(
            "Sorry, I cannot schedule reminders right now. Please try again later or contact the administrator.",
            reply_markup=REPLY_KEYBOARD # Keep keyboard visible on error
        )
        return

    job_data = {'message_text': user_message, 'original_message_id': message_id}
    jobs_scheduled = 0
    first_interval_minutes = None

    for interval in REMINDER_INTERVALS_SECONDS:
        job_name = f"reminder_{chat_id}_{message_id}_{interval}s"
        context.job_queue.run_once(
            send_reminder,
            when=interval,
            chat_id=chat_id,
            data=job_data.copy(),
            name=job_name
        )
        jobs_scheduled += 1
        if jobs_scheduled == 1:
             first_interval_minutes = int(interval / 60)
        logger.info(f"Scheduled job '{job_name}' for chat {chat_id} to run in {interval} seconds.")

    if jobs_scheduled > 0:
        await update.message.reply_text(
            f"✅ Added '{user_message}' to your learning dictionary!\n"
            f"First reminder in about {first_interval_minutes} minutes. "
            f"Total {jobs_scheduled} reminders scheduled.",
            reply_markup=REPLY_KEYBOARD # Keep keyboard visible after scheduling
        )
    else:
         await update.message.reply_text(
             "Couldn't schedule any reminders for some reason.",
             reply_markup=REPLY_KEYBOARD # Keep keyboard visible
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


# --- Main Bot Logic ---

def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")

    if not BOT_TOKEN:
        logger.error("FATAL: Bot token not configured.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Register handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # --- Handler for the "Learning Dictionary" button ---
    # This listens for the specific text sent when the reply keyboard button is pressed.
    # We use filters.Regex to match the exact button text. The '^' and '$' ensure it matches the whole message.
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        show_dictionary_command
    ))

    # --- Handler for OTHER text messages (for scheduling reminders) ---
    # This must come *after* the specific dictionary button handler.
    # It handles any text message that IS NOT a command and IS NOT the dictionary button text.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{re.escape(LEARNING_DICT_BUTTON_TEXT)}$'),
        schedule_reminders
    ))

    # Register the error handler
    application.add_error_handler(error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("Bot stopped.")


if __name__ == '__main__':
    main()
