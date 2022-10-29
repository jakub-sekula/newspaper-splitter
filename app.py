from flask import Flask, Response, request, jsonify
from utils import (
    dropbox_download_file,
    update_folder_cursor,
    zip_file,
    split_file,
    check_for_updates
)
import sqlite3
import os
from mailer import send_mail
import threading
import logging
import sys
from hashlib import sha256
import hmac
import auth

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler(sys.stdout)],
)
logger.info("Starting app newspaper-splitter...")

APP_PATH = os.getenv("DROPBOX_FOLDER_PATH")
folder_cursor = None

# Database connection and tables setup
logger.debug("Connecting to database...")
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

logger.debug("Database tables set up successfully!")

# Initialise the auth object, which keeps track of tokens
auth = auth.AuthProvider(db)

# Only bother with cursor setup if auth passed internal checks
if auth.initialised:
    logger.debug(f"Auth provider initialised succesfully!")

    update_folder_cursor(APP_PATH,auth.access_token,db)

    # If none of the above throw an exception on startup, then the app is ready to go
    logger.info("App initialised successfully")

logger.info("Starting Flask app and listening for events...")
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    """Respond to the webhook verification (GET request) by echoing back the challenge parameter."""

    logger.info("Webhook verification request received!")
    resp = Response(request.args.get("challenge"))
    resp.headers["Content-Type"] = "text/plain"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    return resp


@app.route("/authorise", methods=["GET"])
def authorise():
    """Refetch the refresh and access token (needs interaction from the user)"""

    logger.debug("Authorisation request received!")
    code = request.args.get("code")
    auth.update_refresh_token(code)

    # When new tokens are retrieved, refresh the cursors in case they are missing
    # and couldn't be retrieved at the start of the program
    update_folder_cursor(APP_PATH,auth.access_token,db)

    data = {"message": "Re-authorisation successful. You can close this tab."}

    return jsonify(data), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    logger.info(f"Webhook activated!")

    folder_cursor = db.execute(f"SELECT cursor FROM cursors WHERE folder is '{APP_PATH}'").fetchone()[0]
    logger.debug(f"Folder cursor in webhook is: {folder_cursor}")

    # Verify Dropbox signature
    try:
        signature = request.headers.get("X-Dropbox-Signature")
        logger.debug(f"Request signature: {signature}")
        if not hmac.compare_digest(
            signature,
            hmac.new(
                bytes(os.getenv("DROPBOX_APP_SECRET"), "utf-8"),
                request.data,
                sha256,
            ).hexdigest(),
        ):
            logger.warn("Failed to verify Dropbox signature! Returning status 403...")
            return Response(status=403)

        logger.debug(f"Request signature successfully verified!")
    except:
        logger.error("Signature missing from request! Returning status 403...")
        return Response(status=403)

    # Return 403 Unauthorized if the token can't be validated
    if not auth.validate_token():
        return Response(status=403)

    changes = check_for_updates(folder_cursor, db, APP_PATH, auth.access_token)

    if not changes:
        logger.info("Sending response to webhook!")
        return Response(status=200)

    # Extract updated cursor and list of changed files from the update response
    folder_cursor = changes["cursor"]
    files_list = changes["files_list"]

    # Download the changed files, split them, and send emails
    if files_list:
        for file in files_list:
            filename = file["filename"]
            path = file["path"]

            dropbox_download_file(path, f"downloads/{filename}", auth.access_token)
            zip_file(f"./downloads/{filename}", f"./zips/{filename}.zip")
            split_file(f"./zips/{filename}.zip", "./split_zips", eval(os.getenv("MAX_FILE_SIZE")))

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
            logger.error(f"Error while sending the emails: {e}")

    logger.info("Sending response to webhook!")
    return Response(status=200)

if __name__ == "__main__":
    logger.warning("You should not be running the script directly! (Use gunicorn)")
    app.run(host="0.0.0.0", debug=True)
