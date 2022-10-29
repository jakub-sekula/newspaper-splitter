from urllib.parse import urlencode, urlunsplit
from dotenv import load_dotenv, set_key
import os
import logging
import time
import requests

load_dotenv()
logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(levelname)s] %(message)s")

class AuthProvider:
    def __init__(self, database):
        self.database = database
        self.app_key = os.getenv("DROPBOX_APP_KEY")
        self.app_secret = os.getenv("DROPBOX_APP_SECRET")
        self.access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
        self.refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
        self.initialised = True if self.access_token and self.refresh_token else False

        query = urlencode(
            {
                "client_id": self.app_key,
                "token_access_type": "offline",
                "response_type": "code",
                "redirect_uri": os.getenv("REAUTH_URL"),
            }
        )

        self.auth_url = urlunsplit(
            ("https", "dropbox.com", "oauth2/authorize", query, "")
        )

        if not self.refresh_token:
            logger.critical(
                "Refresh token missing from .env! You need to go through the auth flow and reauthorise."
            )
            logger.critical(
                f"Please go to {self.auth_url} to get a new refresh and access token."
            )
            return

        self.validate_token()


    def show_tokens(self):
        """Shows the refresh and access tokens within the AuthProvider object
        """
        logger.debug(f"Access token in memory is: {self.access_token}")
        logger.debug(f"Refresh token in memory is: {self.refresh_token}")

    def validate_token(self):
        """Performs checks on the database and in-memory tokens.
        If any of them is found to be invalid, the token is disarded and a new one is fetched.

        Returns:
            Boolean: True if validation passed, False on errors
        """
        logger.debug("Checking access token...")

        # Check for token in database
        try:
            if not self.token_in_database():
                logger.warning("Token missing from database! Fetching new token...")
                self.get_access_token()
                return True
        except Exception as e:
            logger.error(f"Error while retrieving token from database! Error message: {e}")

        # Check if token expired
        try:
            token_expired = time.time() > self.database.execute(f"SELECT * FROM access_tokens").fetchone()[2]

            if token_expired:
                logger.warning("Token expired! Fetching new token...")
                self.get_access_token()
                return True

            logger.debug("Token not expired!")
        except Exception as e:
            logger.error(
                f"Could not verify the token expiration date, it may be corrupted or missing from database! Error message: {e}"
            )

        # If offline checks are passed, validate the token online
        try:
            logger.debug("Checking validity online with Dropbox API...")
            validation_status = requests.post(
                "https://api.dropboxapi.com/2/check/user",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json ; charset=utf-8",
                },
                json={"": ""},
            ).status_code

            if not validation_status == 200:
                logger.warning("Token invalid! Fetching new token...")
                self.get_access_token()
                return True
                
            logging.debug("Token validated successfully!")
            return True
        except Exception as e:
            logger.error(f"There has been an error whle validating the token: {e}")
            return False

    def get_access_token(self):
        """Requests new access token using the loaded refresh token

        Raises:
                Exception: _description_

        Returns:
                dict: {'token': string, 'expires': float, 'requested': float}
        """
        logger.debug(
            f"Requesting new access token using refresh token {self.refresh_token}"
        )

        try:
            token_response = requests.post(
                "https://api.dropboxapi.com/oauth2/token",
                data={
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                auth=(self.app_key, self.app_secret),
            )

            if not token_response.ok:
                raise Exception(
                    f"Bad response received from Dropbox API (status {token_response.status_code})\nResponse: {token_response.json()}"
                )

            new_token = {
                "token": token_response.json()["access_token"],
                "expires": time.time() + token_response.json()["expires_in"],
                "requested": time.time(),
            }

            self.update_access_token(new_token)

            return new_token

        except Exception as e:
            logger.error(f"Error in get_access_token function: {e}")
            return None

    def update_access_token(self, new_token):
        self.access_token = new_token["token"]
        set_key(".env", "DROPBOX_ACCESS_TOKEN", self.access_token)
        with self.database:
            self.database.execute("DELETE FROM access_tokens")
            self.database.execute(
                """INSERT INTO access_tokens VALUES (?,?,?)""",
                (
                    new_token["token"][-10:-1],
                    new_token["requested"],
                    new_token["expires"],
                ),
            )

        logger.info(f"New token {self.access_token[-10:-1]} has been added to database")

    def update_refresh_token(self, authorization_code):
        refresh_token_response = requests.post(
            "https://api.dropboxapi.com/oauth2/token",
            params={
                "code": authorization_code,
                "grant_type": "authorization_code",
                "redirect_uri": "https://seklerek.ddns.net/authorise",
            },
            auth=(self.app_key, self.app_secret),
        )

        json = refresh_token_response.json()

        logger.debug(
            f"Refresh token status ({refresh_token_response.status_code}), response: {json}"
        )

        if not refresh_token_response.status_code == 200:
            logger.error()
            return False

        self.refresh_token = refresh_token_response.json()["refresh_token"]
        logger.debug(f"Setting .env refresh token to {json['refresh_token']}")
        set_key(".env", "DROPBOX_REFRESH_TOKEN", json["refresh_token"])

        self.validate_token()

    def token_in_database(self):
        return self.database.execute(f"SELECT * FROM access_tokens").fetchone()


#
