import asyncio
import os
import threading

import db

db.init()

from admin import app  # noqa: E402
from bot import run    # noqa: E402


def web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=web, daemon=True).start()
    asyncio.run(run())
