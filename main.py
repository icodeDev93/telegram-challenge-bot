import os
import telebot
from dotenv import load_dotenv
from sheets import SheetsClient
from datetime import datetime

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
CREDS = os.getenv("GOOGLE_CREDS_JSON")
FOLDER_ID = os.getenv("FOLDER_ID")

bot = telebot.TeleBot(TOKEN)

# match new SheetsClient signature
# sheets = SheetsClient(SHEET_ID, CREDS, FOLDER_ID)

# Initialize SheetsClient with error handling
try:
    sheets = SheetsClient(SHEET_ID, CREDS, FOLDER_ID)
except Exception as e:
    print(f"Failed to initialize SheetsClient: {e}")
    raise  # Re-raise for debugging; consider handling gracefully in production

# in-memory per-user state to store current_week for user session
user_state = {}  # user_id -> {'week_number': int, 'awaiting_photo': bool}

# keyboard helper
def main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('Partake in the challenge', 'Check Points')
    markup.add('Leaderboard', 'Main Channel')
    return markup

@bot.message_handler(commands=['start'])
def handle_start(message):
    user = message.from_user
    current_week = sheets.get_current_week()
    if current_week is None:
        bot.reply_to(message, "Current week is not set. Contact admin.")
        return
    user_state[user.id] = {'week_number': current_week, 'awaiting_photo': False}
    text = f"Hi {user.first_name or user.username}! How may I assist you?"
    bot.send_message(chat_id=message.chat.id, text=text, reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == 'Partake in the challenge')
def partake(message):
    user = message.from_user
    state = user_state.get(user.id)
    if not state:
        bot.send_message(message.chat.id, "Please /start first.")
        return
    state['awaiting_photo'] = True
    bot.send_message(message.chat.id, "Upload a screenshot of your answer")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user = message.from_user
    state = user_state.get(user.id)
    if not state or not state.get('awaiting_photo'):
        bot.send_message(message.chat.id, "If you want to submit, press 'Partake in the challenge' first.")
        return

    try:
        # download the file bytes from Telegram
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_path = file_info.file_path  # path on telegram servers
        # build download URL (bot token used)
        download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        import requests, os
        resp = requests.get(download_url, stream=True)
        resp.raise_for_status()
        file_bytes = resp.content

        # upload to Drive using SheetsClient helper
        # create a readable filename (preserve extension if possible)
        ext = os.path.splitext(file_path)[1] or ".jpg"
        filename = f"{user.id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}{ext}"

        drive_url = sheets.upload_photo_to_drive(file_bytes, filename)

        # write Drive URL into the Main sheet (answer column)
        sheets.insert_main_submission(
            user_id=user.id,
            username=user.username or user.first_name,
            week_number=state['week_number'],
            answer=drive_url
        )

        state['awaiting_photo'] = False
        bot.send_message(message.chat.id, "Submission received. Thanks and good luck!")

    except Exception as e:
        # surface helpful error to admin/logs but keep user-facing message simple
        print("[handle_photo] error:", e)
        bot.send_message(message.chat.id, "Failed to process submission. Try again or contact admin.")

@bot.message_handler(func=lambda m: m.text == 'Check Points')
def check_points(message):
    user = message.from_user
    total, rank = sheets.get_user_points_and_rank(user.id)
    rank_text = rank if rank is not None else "unranked"
    bot.send_message(message.chat.id, f"You have {total} points and you rank number {rank_text} on the leaderboard!")

@bot.message_handler(func=lambda m: m.text == 'Leaderboard')
def send_leaderboard(message):
    top = sheets.get_leaderboard_top(10)
    if not top:
        bot.send_message(message.chat.id, "Leaderboard is empty.")
        return
    lines = []
    for i, row in enumerate(top, start=1):
        username = row.get("username") or "N/A"
        pts = row.get("total_points")
        lines.append(f"{i}. {username} — {pts}")
    bot.send_message(message.chat.id, "Top 10:\n" + "\n".join(lines))

@bot.message_handler(func=lambda m: m.text == 'Main Channel')
def do_exit(message):
    bot.send_message(message.chat.id, "Click on the link below to return to the main channel.")
    # send a link to your channel or use a channel username
    bot.send_message(message.chat.id, "https://t.me/deepfunding")

if __name__ == "__main__":
    print("Bot running (polling). Press Ctrl-C to stop.")
    #bot.polling(non_stop=True)
