# from extensions import db
# from models import EventResponse

# emoji_to_int = {
#     "😫": "1",
#     "😔": "2",
#     "😐": "3",
#     "🙂": "4",
#     "✨": "5"
# }

# def run_fix():
#     responses = EventResponse.query.all()

#     for r in responses:
#         if r.answer in emoji_to_int:
#             print(f"Fixing {r.answer} -> {emoji_to_int[r.answer]}")
#             r.answer = emoji_to_int[r.answer]

#     db.session.commit()
#     print("Done updating mood data!")

# if __name__ == "__main__":
#     run_fix()

import sys
import os

# add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from extensions import db
from models import EventResponse

emoji_to_int = {
    "😫": "1",
    "😔": "2",
    "😐": "3",
    "🙂": "4",
    "✨": "5"
}

with app.app_context():

    responses = EventResponse.query.all()

    for r in responses:
        if r.answer in emoji_to_int:
            print(f"Fixing {r.answer} -> {emoji_to_int[r.answer]}")
            r.answer = emoji_to_int[r.answer]

    db.session.commit()

    print("Done updating mood data!")