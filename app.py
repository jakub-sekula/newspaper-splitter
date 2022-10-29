from flask import Flask, Response, request, jsonify
from utils import (
    get_folder_cursor,
    dropbox_download_file,
    zip_file,
    file_split,
    check_for_updates
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
import auth

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    level=logging.DEBUG,
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler(sys.stdout)],
)

logging.info("Starting app newspaper-splitter...")


APP_PATH = os.getenv("DROPBOX_FOLDER_PATH")
AUTH_URL = f"https://www.dropbox.com/oauth2/authorize?client_id={os.getenv('DROPBOX_APP_KEY')}&token_access_type=offline&response_type=code&redirect_uri={'https://seklerek.ddns.net/authorise'}"
folder_cursor = None
access_token = None

# Database connection and tables setup
logging.debug("Connecting to database...")
db = sqlite3.connect("store.db")

with db:
    db.execute(
        """CREATE TABLE IF NOT EXISTS cursors (
        folder text,
        cursor text,
        timestamp real
    )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS access_tokens (
        token_last10 text,
        token_requested real,
        token_expires real
    )"""
    )
logging.debug("Database tables set up successfully!")

auth = auth.AuthProvider(db)

# Initialise app only if refresh token is available
if auth.initialised:
    logging.info(f"Auth provider initialised succesfully!")
    try:
        # Retrieve Dropbox folder cursor or get a new one if missing
        cursors_in_database = db.execute(
            f"SELECT * FROM cursors WHERE folder='{APP_PATH}'"
        ).fetchall()
        logging.debug(f"Cursors in database: {cursors_in_database}")

        if not cursors_in_database:
            logging.debug("No cursors found in database! Retrieving fresh cursor...")
            folder_cursor = get_folder_cursor(APP_PATH, auth.access_token)["cursor"]
            logging.debug(f"Response from get_folder_cursor: {folder_cursor}")
            logging.debug(f"Folder cursor for {APP_PATH} is {folder_cursor}")
            with db:
                db.execute(
                    f"INSERT INTO cursors VALUES (?,?,?)",
                    (APP_PATH, folder_cursor, time.time()),
                )
        else:
            folder_cursor = db.execute(
                f"SELECT cursor FROM cursors WHERE folder IS '{APP_PATH}'"
            ).fetchone()[0]

        # If none of the above throw an exception on startup, then the app is ready to go
        logging.info("App initialised successfully")

    except Exception as e:
        logging.error(f"Error while fetching cursor: {e}")


logging.info("Starting Flask app and listening for events...")
app = Flask(__name__)


@app.route("/webhook", methods=["GET"])
def verify():
    logging.info("Webhook verification request received!")
    """Respond to the webhook verification (GET request) by echoing back the challenge parameter."""

    resp = Response(request.args.get("challenge"))
    resp.headers["Content-Type"] = "text/plain"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    return resp


@app.route("/authorise", methods=["GET"])
def authorise():
    logging.debug("Authorisation request received!")
    code = request.args.get("code")

    auth.update_refresh_token(code)

    try:
        # Retrieve Dropbox folder cursor or get a new one if missing
        cursors_in_database = db.execute(
            f"SELECT * FROM cursors WHERE folder='{APP_PATH}'"
        ).fetchall()
        logging.debug(f"Cursors in database: {cursors_in_database}")

        if not cursors_in_database:
            logging.debug("No cursors found in database! Retrieving fresh cursor...")
            folder_cursor = get_folder_cursor(APP_PATH, auth.access_token)["cursor"]
            logging.debug(f"Response from get_folder_cursor: {folder_cursor}")
            logging.debug(f"Folder cursor for {APP_PATH} is {folder_cursor}")
            with db:
                db.execute(
                    f"INSERT INTO cursors VALUES (?,?,?)",
                    (APP_PATH, folder_cursor, time.time()),
                )
        else:
            folder_cursor = db.execute(
                f"SELECT cursor FROM cursors WHERE folder IS '{APP_PATH}'"
            ).fetchone()[0]

        # If none of the above throw an exception on startup, then the app is ready to go
        logging.info("App initialised successfully")

    except Exception as e:
        logging.error(f"Error while fetching cursor: {e}")

    data = {"message": "Re-authorisation successful. You can close this tab."}

    return jsonify(data), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info(f"Webhook activated!")

    folder_cursor = db.execute(f"SELECT cursor FROM cursors WHERE folder is '{APP_PATH}'").fetchone()[0]
    logging.debug(f"Folder cursor in webhook is: {folder_cursor}")

    # Verify Dropbox signature
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
            logging.warn("Failed to verify Dropbox signature! Returning status 403...")
            return Response(status=403)
    except:
        logging.error("Signature missing from request! Returning status 403...")
        return Response(status=403)

    if not auth.validate_token():
        return Response(status=403)

    logging.debug(f"Request signature {signature} successfully verified!")

    changes = check_for_updates(folder_cursor, db, APP_PATH, auth.access_token)
    folder_cursor = changes["cursor"]
    files_list = changes["files_list"]

    if len(files_list) != 0:

        for file in files_list:
            path = file["path"]
            filename = file["filename"]

            logging.info(f"Downloading file {filename} from {path}")
            dropbox_download_file(path, f"downloads/{filename}", auth.access_token)

            logging.debug(f"Zipping file {filename}...")
            zip_file(f"./downloads/{filename}", f"./zips/{filename}.zip")

            logging.debug(f"Splitting file {filename}")
            file_split(f"./zips/{filename}.zip", "./split_zips", 1 * 1024 * 1024)

            try:
                for file in os.listdir("split_zips"):
                    if file.split(".")[0] == filename.split(".")[0] and file[0] != ".":
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
