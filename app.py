from flask import Flask, Response, request
from dotenv import load_dotenv
from utils import (
    get_folder_cursor,
    dropbox_download_file,
    zip_file,
    file_split,
    check_for_updates,
    validate_access_token,
)
import sqlite3
import os
import time
from mailer import send_mail
import threading
import logging
import sys
from hashlib import sha256
import hmac

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler(sys.stdout)],
)

APP_PATH = ""
ACCESS_TOKEN = ""
FOLDER_CURSOR = ""

# Initial setup steps
try:
    logging.debug("Loading configuration from .env file...")
    load_dotenv()
    logging.debug("Loading access token from .env file...")
    ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
    logging.debug(f"Access token loaded from .env: {ACCESS_TOKEN[-10:-1]}")
    logging.debug("Loading app path from .env file...")
    APP_PATH = os.getenv("DROPBOX_FOLDER_PATH")
    logging.debug(f"App path loaded from .env: {APP_PATH}")
except Exception as e:
    logging.error("There was an issue loading configuration from the .env file!")

# Initialise app
try:
    logging.info("Starting app newspaper-splitter...")

    # Database connection and tables setup
    try:
        logging.debug("Connecting to database...")
        conn = sqlite3.connect("store.db")
        c = conn.cursor()
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
        logging.error(f"Error while connecting to database: {e}")

    # Initialise access token and save it to database
    ACCESS_TOKEN = validate_access_token(ACCESS_TOKEN, conn, c)

    # Retrieve Dropbox folder cursor or get a new one if missing
    try:
        c.execute(f"SELECT * FROM cursors WHERE folder='{APP_PATH}'")
        cursors_in_database = c.fetchall()
        if not cursors_in_database:
            FOLDER_CURSOR = get_folder_cursor(APP_PATH, ACCESS_TOKEN)["cursor"]
            logging.debug(f"Folder cursor for {APP_PATH} is {FOLDER_CURSOR}")
            c.execute(
                f"INSERT INTO cursors VALUES ('{APP_PATH}', '{FOLDER_CURSOR}',{time.time()})"
            )
            conn.commit()
        else:
            c.execute(f"SELECT cursor FROM cursors WHERE folder IS '{APP_PATH}'")
            FOLDER_CURSOR = c.fetchone()[0]
    except Exception as e:
        logging.error(f"Error while updating cursor. Error message: {e}")

    app = Flask(__name__)
    logging.info("App initialised successfully")

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

        try:
            signature = request.headers.get("X-Dropbox-Signature")
            logging.debug(f"Request signature: {signature}")
            if not hmac.compare_digest(
                signature,
                hmac.new(
                    bytes(os.getenv("DROPBOX_APP_SECRET"), "utf-8"),
                    request.data,
                    sha256,
                ).hexdigest(),
            ):
                logging.warn(
                    "Failed to verify Dropbox signature! Returning status 403..."
                )
                return Response(status=403)
        except:
            logging.error("Signature missing from request! Returning status 403...")
            return Response(status=403)

        logging.debug(f"Request signature {signature} successfully verified!")

        changes = check_for_updates(FOLDER_CURSOR, conn, c, APP_PATH, ACCESS_TOKEN)
        files_list = changes["files_list"]

        if len(files_list) != 0:

            for file in files_list:
                path = file["path"]
                filename = file["filename"]

                logging.info(f"Downloading file {filename} from {path}")
                dropbox_download_file(path, f"downloads/{filename}", ACCESS_TOKEN)
                # threading.Thread(target=dropbox_download_file, args=(path, f"downloads/{filename}", ACCESS_TOKEN)).start()

                logging.debug(f"Zipping file {filename}...")
                zip_file(f"./downloads/{filename}", f"./zips/{filename}.zip")
                # threading.Thread(target=zipfile, args=(f"./downloads/{filename}", f"./zips/{filename}.zip")).start()

                logging.debug(f"Splitting file {filename}")
                file_split(f"./zips/{filename}.zip", "./split_zips", 1 * 1024 * 1024)

                try:
                    for file in os.listdir("split_zips"):
                        if (
                            file.split(".")[0] == filename.split(".")[0]
                            and file[0] != "."
                        ):
                            threading.Thread(
                                target=send_mail,
                                args=(
                                    os.path.join("split_zips", file),
                                    os.getenv("SMTP_RECEIVER"),
                                ),
                            ).start()
                except Exception as e:
                    logging.error(e)

        logging.info("Sending response to webhook!")
        return Response(status=200)

    if __name__ == "__main__":
        logging.warning("You should not be running the script directly! (Use gunicorn)")
        app.run(host="0.0.0.0", debug=True)

except Exception as e:
    logging.critical(f"App failed to initialise. Error message: {e}")
    raise SystemExit
