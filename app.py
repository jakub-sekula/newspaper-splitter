from flask import Flask, Response, request
from dotenv import load_dotenv, set_key
from utils import (
    get_folder_cursor,
    get_access_token,
    dropbox_list_files_continue,
    dropbox_download_file,
    zipfile,
    file_split
)
import sqlite3
import os
import time
from mailer import send_mail
import threading
import logging
import sys

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler(sys.stdout)],
)
logging.info("Starting app newspaper-splitter...")

try:
    load_dotenv()
    logging.debug('Loaded configuration from .env file')
    ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
    logging.debug(f"Access token loaded from .env: {ACCESS_TOKEN[-10:-1]}")
except Exception as e:
    ACCESS_TOKEN = ""
    logging.error('Could not load configuration fron .env file!')

APP_PATH = os.getenv("DROPBOX_FOLDER_PATH")
   

folder_cursor = None

logging.debug("Connecting to database...")
conn = sqlite3.connect("store.db")
c = conn.cursor()

try:
    c.execute(
        """CREATE TABLE IF NOT EXISTS cursors (
		folder text,
		cursor text,
		timestamp real
	)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS access_tokens (
        token_last10 text,
		token_requested real,
		token_expires real
	)"""
    )
    logging.debug("Database tables set up successfully!")
except Exception as e:
    logging.error(e)


def validate_access_token():
    global ACCESS_TOKEN
    logging.info("Validating access token...")
    try:
        c.execute(f"SELECT * FROM access_tokens")
        results = c.fetchall()

        if len(results) == 0:
            logging.warn("Token missing from database! Requesting new token...")
            resp = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))
            c.execute(
                f"INSERT INTO access_tokens VALUES ('{resp['token'][-10:-1]}', {resp['requested']},{resp['expires']})"
            )
            ACCESS_TOKEN = resp["token"]
            set_key(".env", "DROPBOX_ACCESS_TOKEN", ACCESS_TOKEN)
            conn.commit()
            logging.info(
                f"New token {resp['token'][-10:-1]} has been added to database"
            )
            return

        resp = results[0]
        is_token_expired = time.time() > resp[2]

        if is_token_expired is True:
            logging.warn("Token expired! Requesting new token...")
            resp = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))
            c.execute(
                f"""UPDATE access_tokens
                    SET token_last10 = '{resp['token'][-10:-1]}',
                        token_requested = {resp['requested']},
                        token_expires = {resp['expires']}
                    WHERE token_last10 IS '{os.getenv("DROPBOX_ACCESS_TOKEN")[-10:-1]}'
                """
            )
            ACCESS_TOKEN = resp["token"]
            set_key(".env", "DROPBOX_ACCESS_TOKEN", ACCESS_TOKEN)
            conn.commit()
            logging.info(f"Updated token {resp['token'][-10:-1]} has been added to database")
            return

        logging.info(f"Token {ACCESS_TOKEN[-10:-1]} validated - not expired.")
        return

    except Exception as e:
        logging.error(e)
        return


validate_access_token()

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
    logging.error("Error while updating cursor. Error message:")
    logging.error(e)


def check_for_updates(cursor):
    global folder_cursor

    logging.info("Checking for updates...")

    validate_access_token()

    changes = dropbox_list_files_continue(cursor, ACCESS_TOKEN)

    if len(changes["files_list"]) == 0:
        logging.info("No new files added to folder.")

    # Update folder cursor
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
    logging.debug(f"Updated folder cursor to {folder_cursor[-10:-1]}")

    return changes


app = Flask(__name__)
logging.info("App initialised successfully!")


@app.route("/")
def index():
    return (Response(status = 404))


@app.route("/webhook", methods=["GET"])
def verify():
    logging.info("Webhook verification request received!")
    """Respond to the webhook verification (GET request) by echoing back the challenge parameter."""

    resp = Response(request.args.get("challenge"))
    resp.headers["Content-Type"] = "text/plain"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    return resp


@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info(f"Webhook activated!")
    changes = check_for_updates(folder_cursor)

    files_list = changes["files_list"]

    if len(files_list) != 0:

        for file in files_list:
            path = file["path"]
            filename = file["filename"]

            logging.info(f"Downloading file {filename} from {path}")
            dropbox_download_file(path, f"downloads/{filename}", ACCESS_TOKEN)

            logging.debug(f"Zipping file {filename}...")
            zipfile(f"./downloads/{filename}", f"./zips/{filename}.zip")

            logging.debug(f"Splitting file {filename}")
            file_split(f"./zips/{filename}.zip", "./split_zips", 1 * 1024 * 1024)

            for file in os.listdir("split_zips"):
                if file.split(".")[0] == filename.split(".")[0] and file[0] != ".":
                    threading.Thread(
                        target=send_mail, args=(os.path.join("split_zips", file),os.getenv("SMTP_RECEIVER"))
                    ).start()

    logging.info("Sending response to webhook!")
    return Response(status=201)


if __name__ == "__main__":
    logging.warn("You should not be running the script directly! (Use gunicorn)")
    app.run(host="0.0.0.0", debug=True)
