import os
import main
from flask import Flask, request, abort


creds_json_env = os.environ.get("GOOGLE_CREDS_JSON")
if creds_json_env:
    tmp_path = "/tmp/service_account.json"
    with open(tmp_path, "w") as f:
        f.write(creds_json_env)
    os.environ["GOOGLE_CREDS"] = tmp_path


from telebot import types as _types

app = Flask(__name__)

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if WEBHOOK_URL:
   try:
      main.bot.remove_webhook()
      main.bot.set_webhook()
      app.logger.info(f"Webhook se to {WEBHOOK_URL}")
   except Exception as e:
      app.logger.error(f"Faiiled to set webhook: {e}")
else:
      app.logger.error(f"WEBHOOK_URL not set, webhook not configured")

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

# Optional: secret token in path to make URL unguessable
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # e.g. a random string you set in Cloud Run env

def _valid_path():
    # returns True if a secret is required and the request path includes it
    if not WEBHOOK_SECRET:
        return True
    # path will be like /webhook/<secret>
    return request.path.endswith("/" + WEBHOOK_SECRET)

@app.route("/webhook", methods=["POST"])
@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret=None):
    # basic guard
    if not _valid_path():
        abort(403)

    if request.headers.get("content-type") != "application/json":
        abort(403)

    json_string = request.get_data().decode("utf-8")
    try:
        update = _types.Update.de_json(json_string)
        main.bot.process_new_updates([update])
    except Exception as e:
        # log server-side; return 200 so Telegram won't retry excessively in loop
        app.logger.exception("Failed to process update: %s", e)
        return "", 200
    return "", 200
