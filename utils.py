from dotenv import load_dotenv, set_key
import os
import requests
import dropbox
from dropbox.exceptions import AuthError
from pprint import pprint
import time
import logging
from zipfile import ZipFile

load_dotenv()




def dropbox_connect(access_token):
	"""Create a connection to Dropbox."""

	try:
		logging.debug(
			f"Attempting to connect to Dropbox API using access token {access_token[-10:-1]}"
		)
		dbx = dropbox.Dropbox(access_token)
		logging.debug("Dropbox API connection successful")
	except AuthError as e:
		logging.error(
			f"Error connecting to Dropbox with access token {access_token[-10:-1]}. Error message:"
		)
		logging.error(e)
	return dbx


def dropbox_list_files_continue(cursor, access_token):
	has_more = True

	dbx = dropbox_connect(access_token)

	while has_more:
		try:
			response = dbx.files_list_folder_continue(cursor)

			files_list = []
			for file in response.entries:
				if isinstance(file, dropbox.files.FileMetadata):
					metadata = {
						"filename": file.name,
						"path": file.path_display,
						"client_modified_at": file.client_modified,
						"server_modified_at": file.server_modified,
					}
					files_list.append(metadata)

			has_more = response.has_more
			return {
				"cursor": response.cursor,
				"files_list": files_list,
				"entries": response.entries,
			}

		except Exception as e:
			logging.error("Error getting list of files from Dropbox: " + str(e))
			break


def dropbox_download_file(dropbox_file_path, local_file_path, access_token):
	"""Download a file from Dropbox to the local machine."""
	logging.debug(f"Downloading file {dropbox_file_path} from Dropbox...")
	try:
		dbx = dropbox_connect(access_token)

		with open(local_file_path, "wb") as f:
			metadata, result = dbx.files_download(path=dropbox_file_path)
			f.write(result.content)
	except Exception as e:
		logging.error(f"Error downloading file {dropbox_file_path} from Dropbox: ")
		logging.error(e)


def zip_file(file, outputZIP="attachment.zip"):
	logging.debug(f"Now zipping file {file} to {outputZIP}")

	try:
		with ZipFile(outputZIP, "w") as zip:
			zip.write(file)
			logging.debug("All files zipped successfully!")
	except Exception as e:
		logging.error(e)


# Buffer size 50 GB
BUF = 1 * 1024 * 1024 * 1024


def file_split(file, output_directory, max_size):
	"""Split file into pieces, every size is  MAX = 15*1024*1024 Byte"""
	chapters = 1
	uglybuf = ""
	with open(file, "rb") as src:
		while True:
			filename = f"{(os.path.splitext(file)[0])}.z0{chapters}".split("/")[-1]
			tgt = open(f"{os.path.join(output_directory, filename)}", "wb")
			logging.debug(f"Writing {filename}...")
			written = 0
			while written < max_size:
				if len(uglybuf) > 0:
					tgt.write(uglybuf)
				tgt.write(src.read(min(BUF, max_size - written)))
				written += min(BUF, max_size - written)
				uglybuf = src.read(1)
				if len(uglybuf) == 0:
					break
			tgt.close()
			if len(uglybuf) == 0:
				break
			chapters += 1

def get_access_token(REFRESH_TOKEN):
	logging.debug(
		f"Requesting new access token using refresh token {REFRESH_TOKEN[-10:-1]}"
	)
	try:
		logging.debug(f"Sending POST request with refresh token {REFRESH_TOKEN}")
		res = requests.post(
			"https://api.dropboxapi.com/oauth2/token",
			data={"refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"},
			auth=(os.getenv("DROPBOX_APP_KEY"), os.getenv("DROPBOX_APP_SECRET")),
		)

		payload = {
			"token": res.json()["access_token"],
			"expires": time.time() + res.json()["expires_in"],
			"requested": time.time(),
		}
		logging.debug(f"Returning payload: {payload}")
		return payload
	except Exception as e:
		logging.error(f"Error in get_access_token function: {e}")

def validate_access_token(db, refresh_token_response=None):
	logging.debug("Checking access token...")

	# If a new refresh token has just been requested, use its response to update the access token
	if refresh_token_response:
		new_token = refresh_token_response['access_token']
		logging.debug(f"new_token = {new_token}")

		requested = time.time()
		logging.debug(f"requested = {requested}")

		expires = requested + refresh_token_response['expires_in']
		logging.debug(f"expires = {expires}")

		with db:
			db.execute("INSERT INTO access_tokens VALUES (?,?,?)", (new_token[-10:-1], requested, expires))
			logging.info(f"New token {new_token[-10:-1]} has been added to database")

		logging.debug(f"Setting .env key DROPBOX_ACCESS_TOKEN to {new_token}")      
		set_key(".env", "DROPBOX_ACCESS_TOKEN", new_token)
		logging.debug("Access token successfully updated with update_token_in_database")
		return

	# Otherwise, check if a token exists in the environment and database
	load_dotenv()
	token = os.getenv("DROPBOX_ACCESS_TOKEN")
	db_token = db.execute(f"SELECT * FROM access_tokens").fetchall()

	# Check expiration date only if the database contains a token
	is_token_expired = time.time() > db_token[0][2] if db_token else None
	logging.debug(f"is_token_expired: {is_token_expired}, seconds left: {db_token[0][2] - time.time()}")

	logging.debug(f"Results of token search in database: {db_token}")

	# If there is no token in the .env, get a fresh one
	if not token:
		logging.warn("Token missing when app initialised! Requesting new token...")
		# if not os.getenv("DROPBOX_REFRESH_TOKEN"):

		new_token = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))
		logging.debug(f"Response returned by get_access_token: {new_token}")
		with db:
			db.execute(f"DELETE FROM access_tokens")
			db.execute(
				f"INSERT INTO access_tokens VALUES (?,?,?)",
				(new_token['token'][-10:-1], new_token['requested'],new_token['expires']))
			logging.info(f"New token {new_token['token'][-10:-1]} has been added to database")
		logging.debug(f"Setting .env key DROPBOX_ACCESS_TOKEN to {new_token['token']}")
		set_key(".env", "DROPBOX_ACCESS_TOKEN", new_token["token"])
		return

	# Is there is no token in the database, get a fresh one
	if not db_token:
		logging.warn("Token missing from database! Requesting new token...")
		new_token = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))
		logging.debug(f"Response returned by get_access_token: {new_token}")
		with db:
			db.execute("INSERT INTO access_tokens VALUES (?,?,?)", 
						new_token['token'][-10:-1], new_token['requested'],new_token['expires'])
			logging.info(f"New token {new_token['token'][-10:-1]} has been added to database")
		logging.debug(f"Setting .env key DROPBOX_ACCESS_TOKEN to {new_token['token']}")      
		set_key(".env", "DROPBOX_ACCESS_TOKEN", new_token["token"])
		return
		

	if is_token_expired:
		logging.warn("Token expired! Requesting new token...")
		new_token = get_access_token(os.getenv("DROPBOX_REFRESH_TOKEN"))
		# with db:
		db.execute(
			f"""UPDATE access_tokens
				SET token_last10 = ?, token_requested = ?, token_expires = ?
				WHERE token_last10 IS ?""", 
				(new_token['token'][-10:-1],new_token['requested'],new_token['expires'],os.getenv("DROPBOX_ACCESS_TOKEN")[-10:-1])
				)
		db.commit()
		logging.info(f"Updated token {new_token['token'][-10:-1]} has been added to database")
		logging.debug(f"Setting .env key DROPBOX_ACCESS_TOKEN to {new_token['token']}")
		set_key(".env", "DROPBOX_ACCESS_TOKEN", new_token["token"])
		return

	logging.info(f"Token {token[-10:-1]} validated - not expired.")
	return

def get_folder_cursor(path):
	load_dotenv()
	logging.debug("Running get_folder_cursor...")
	access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
	dbx = dropbox_connect(access_token)

	try:
		logging.debug(
			f"Requesting cursor from Dropbox on path {path} using access token {access_token}"
		)
		cursor = dbx.files_list_folder(path).cursor
		response = {"cursor": cursor}
		logging.debug(f"Returning response from cursor request: {response}")
		return response

	except Exception as e:
		print("Error getting cursor from Dropbox: " + str(e))

def check_for_updates(cursor, conn, APP_PATH):

	validate_access_token(conn)

	token = os.getenv("DROPBOX_ACCESS_TOKEN")

	logging.info(f"Checking folder {APP_PATH} for updates...")

	changes = dropbox_list_files_continue(cursor, token)

	if not changes["files_list"]:
		logging.info("No new files added to folder.")

	# Update folder cursor in database
	with conn:
		conn.execute(
			f"""
				UPDATE cursors
				SET folder = '{APP_PATH}',
					cursor = '{changes["cursor"]}',
					timestamp = {time.time()}
				WHERE folder IS '{APP_PATH}'
			"""
		)

	logging.debug(f"Updated folder cursor in database to {changes['cursor'][-10:-1]}")

	return changes
