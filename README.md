# Telegram Spaced Repetition Bot (Demo v6)

This Telegram bot helps users learn new English words and phrases using the Spaced Repetition System (SRS). It allows users to add vocabulary, receive reminders at increasing intervals, get phonetic clues, translations, AI-powered explanations, and manage their learning dictionary with sorting options.

## Features

*   **Spaced Repetition System (SRS):** Schedules reminders for words/phrases at optimized intervals (1 min, 1 day, 2 days, etc.) to enhance long-term memory.
*   **Add Words/Phrases:** Users can send any text message to the bot to add it to their learning list.
*   **Learning Dictionary:**
    *   View all currently learned words.
    *   See the number of reminders left for each word.
    *   See an estimate of when the next reminder is due.
    *   **Sortable List:** Users can sort the dictionary view. The primary sort option is by a "pronunciation ease" heuristic (shorter words with fewer vowels first). Users can also toggle back to a default A-Z sort.
*   **Interactive Reminders:** Reminder messages come with inline buttons:
    *   **🗑️ Delete Word:** Allows users to remove a word from their learning list through a confirmation step.
    *   **💡 Clue/Translate:** Provides a phonetic clue (often IPA for the first word using `eng_to_ipa`) and translations into several popular languages (using the `translate` library).
    *   **✨ Explain (AI):** (If configured) Provides an AI-generated explanation and example sentence for the word/phrase using OpenAI's GPT API.
*   **Persistent Reply Keyboard:** Easy access to the "📚 Learning Dictionary".
*   **Commands:**
    *   `/start`: Welcome message.
    *   `/help`: Detailed information about bot features and usage.

## Technical Aspects & Setup

### 1. Python Version

*   Developed and tested with Python 3.10+. The provided instructions assume a `python3` command is available and points to a suitable version (e.g., 3.13 as used in development).

### 2. Dependencies

The bot relies on several Python libraries. Install them using pip:

```bash
# Core Telegram Bot library with JobQueue for scheduled reminders
pip3 install python-telegram-bot[job-queue]

# For phonetic clues (International Phonetic Alphabet)
pip3 install eng_to_ipa

# For translation functionality
pip3 install translate

# For OpenAI GPT integration (optional, but code is present)
pip3 install openai

# The 'requests' library is often a dependency of the above, but install if needed
pip3 install requests 
