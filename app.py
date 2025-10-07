import os
import sys
import traceback
from datetime import datetime
from flask import Flask, request, abort
from telebot import types as _types

app = Flask(__name__)

# health check
@app.route("/", methods=["GET"])
def index():
    return "OK", 200

# webhook secret
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# lazy import holder
_main = None

def import_main():
    global _main
    if _main is not None:
        return _main
    try:
        # print to stderr so logs appear immediately
        print(f"[{datetime.utcnow().isoformat()}] importing main.py", file=sys.stderr)
        import main as _m
        _main = _m
        print(f"[{datetime.utcnow().isoformat()}] imported main.py OK", file=sys.stderr)
        return _main
    except Exception as e:
        # print full traceback to stderr
        print(f"[{datetime.utcnow().isoformat()}] ERROR importing main.py:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # re-raise so the handler catches and returns 200 (avoids Telegram retry storm)
        raise

def _valid_path():
    if not WEBHOOK_SECRET:
        return True
    return request.path.endswith("/" + WEBHOOK_SECRET)

@app.route("/webhook", methods=["POST"])
@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret=None):
    if not _valid_path():
        abort(403)

    if request.headers.get("content-type") != "application/json":
        abort(403)

    json_string = request.get_data().decode("utf-8")
    try:
        main = import_main()
        update = _types.Update.de_json(json_string)
        main.bot.process_new_updates([update])
    except Exception as e:
        # log full exception; return 200 to avoid retry loops
        print(f"[{datetime.utcnow().isoformat()}] ERROR processing update:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return "", 200
    return "", 200
