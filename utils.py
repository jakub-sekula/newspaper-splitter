import os
import dropbox
from dropbox.exceptions import AuthError
import time
import logging
from zipfile import ZipFile

logger = logging.getLogger(__name__)


def dropbox_connect(access_token):
    """Create a connection to Dropbox."""

    try:
        logger.debug(
            f"Attempting to connect to Dropbox API using access token {access_token[-10:-1]}"
        )
        dbx = dropbox.Dropbox(access_token)
        logger.debug("Dropbox API connection successful")
    except AuthError as e:
        logger.error(
            f"Error connecting to Dropbox with access token {access_token[-10:-1]}. Error message:"
        )
        logger.error(e)
    return dbx

def dropbox_list_files_continue(cursor, access_token):
    has_more = True

    logger.debug(f"Connecting to dropbox using access token {access_token}")
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
            logger.error("Error getting list of files from Dropbox: " + str(e))
            break


def dropbox_download_file(dropbox_file_path, local_file_path, access_token):
    """Download a file from Dropbox to the local machine."""
    logger.debug(f"Downloading file {dropbox_file_path} from Dropbox...")
    try:
        dbx = dropbox_connect(access_token)

        with open(local_file_path, "wb") as f:
            metadata, result = dbx.files_download(path=dropbox_file_path)
            f.write(result.content)
    except Exception as e:
        logger.error(f"Error downloading file {dropbox_file_path} from Dropbox: ")
        logger.error(e)


def zip_file(file, outputZIP="attachment.zip"):
    logger.debug(f"Now zipping file {file} to {outputZIP}")

    try:
        with ZipFile(outputZIP, "w") as zip:
            zip.write(file)
            logger.debug("All files zipped successfully!")
    except Exception as e:
        logger.error(e)


def split_file(file, output_directory, max_size, buffer_size=1 * 1024 * 1024 * 1024):
    """Split file into pieces, every piece is max_size bytes"""
    logger.debug(f"Splitting file {file}")
    chapters = 1
    uglybuf = ""
    with open(file, "rb") as src:
        while True:
            filename = f"{(os.path.splitext(file)[0])}.z0{chapters}".split("/")[-1]
            tgt = open(f"{os.path.join(output_directory, filename)}", "wb")
            logger.debug(f"Writing {filename}...")
            written = 0
            while written < max_size:
                if len(uglybuf) > 0:
                    tgt.write(uglybuf)
                tgt.write(src.read(min(buffer_size, max_size - written)))
                written += min(buffer_size, max_size - written)
                uglybuf = src.read(1)
                if len(uglybuf) == 0:
                    break
            tgt.close()
            if len(uglybuf) == 0:
                break
            chapters += 1


def get_folder_cursor(path, token):
    logger.debug("Running get_folder_cursor...")
    dbx = dropbox_connect(token)

    try:
        logger.debug(
            f"Requesting cursor from Dropbox on path {path} using access token {token}"
        )
        cursor = dbx.files_list_folder(path).cursor
        response = {"cursor": cursor}
        logger.debug(f"Returning response from cursor request: {response}")
        return response

    except Exception as e:
        print("Error getting cursor from Dropbox: " + str(e))

def update_folder_cursor(path, token, db):
    try:
        cursors_in_database = db.execute(
            f"SELECT * FROM cursors WHERE folder='{path}'"
        ).fetchall()
        logger.debug(f"Cursors in database: {cursors_in_database}")

        if not cursors_in_database:
            logger.debug("No cursors found in database! Retrieving fresh cursor...")
            folder_cursor = get_folder_cursor(path, token)["cursor"]
            with db:
                db.execute(
                    f"INSERT INTO cursors VALUES (?,?,?)",
                    (path, folder_cursor, time.time()),
                )
            logger.debug(f"Cursor {folder_cursor} has been added to the database!")
        else:
            folder_cursor = db.execute(
                f"SELECT cursor FROM cursors WHERE folder IS '{path}'"
            ).fetchone()[0]
            logger.debug(f"Cursor for path {path} has been updated to {folder_cursor}!")

    except Exception as e:
        logger.error(f"Error while fetching cursor: {e}")

def check_for_updates(cursor, conn, APP_PATH, token):

    logger.info(f"Checking folder {APP_PATH} for updates...")
    changes = dropbox_list_files_continue(cursor, token)

    if not changes["files_list"]:
        logger.info("No new files added to folder.")
        return False

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

    logger.debug(f"Updated folder cursor in database to {changes['cursor'][-10:-1]}")

    return changes
