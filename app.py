from flask import Flask, Response, request
from dotenv import load_dotenv
from utils import (
    get_folder_cursor,
    get_access_token,
    dropbox_list_files_continue,
    dropbox_download_file,
)
import sqlite3
import os
import time
from zip_splitter import zipfile, file_split


load_dotenv()

APP_PATH = os.getenv("DROPBOX_FOLDER_PATH")
ACCESS_TOKEN = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))

conn = sqlite3.connect("cursor.db")
c = conn.cursor()

try:
    c.execute(
        """CREATE TABLE cursors (
		folder text,
		cursor text,
		timestamp real
	)"""
    )
    print("Created table 'cursors'!")
except Exception as e:
    print("Table 'cursors' found!")

folder_cursor = None


try:
    c.execute(f"SELECT * FROM cursors WHERE folder='{APP_PATH}'")
    db_entries = c.fetchall()

    if len(db_entries) == 0:
        folder_cursor = get_folder_cursor(APP_PATH, ACCESS_TOKEN)["cursor"]
        c.execute(
            f"INSERT INTO cursors VALUES ('{APP_PATH}', '{folder_cursor}',{time.time()})"
        )
        conn.commit()
    else:
        c.execute(f"SELECT cursor FROM cursors WHERE folder IS '{APP_PATH}'")
        folder_cursor = c.fetchone()[0]

except Exception as e:
    print("something got fucked", e)


def check_for_updates(cursor):
    global folder_cursor
    changes = dropbox_list_files_continue(cursor, ACCESS_TOKEN)

    c.execute(
        f"""
			UPDATE cursors
			SET folder = '{APP_PATH}',
				cursor = '{changes["cursor"]}',
				timestamp = {time.time()}
			WHERE folder IS '{APP_PATH}'
		"""
    )
    conn.commit()

    folder_cursor = changes["cursor"]

    return changes


app = Flask(__name__)


@app.route("/")
def index():
    return "<h1>Helllo World!</h1>"


@app.route("/webhook", methods=["GET"])
def verify():
    """Respond to the webhook verification (GET request) by echoing back the challenge parameter."""

    resp = Response(request.args.get("challenge"))
    resp.headers["Content-Type"] = "text/plain"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    return resp


@app.route("/webhook", methods=["POST"])
def webhook():
    print(f"Webhook activated! Received request: ", request.json)
    changes = check_for_updates(folder_cursor)
    print(f"Folder cursor is now: {folder_cursor}")
    print(f"Changes: ", changes["entries"])
    files_list = changes["files_list"]

    for file in files_list:
        path = file["path"]
        filename = file["filename"]
        dropbox_download_file(path, f"downloads/{filename}", ACCESS_TOKEN)

        zipfile(f"./downloads/{filename}", f"./zips/{filename}.zip")

        file_split(f"./zips/{filename}.zip", "./split_zips", 1 * 1024 * 1024)
        # os.remove(f"./zips/{filename}.zip")

    return Response(status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
