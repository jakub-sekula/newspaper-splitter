from dotenv import load_dotenv
import os
import requests
import dropbox
from dropbox.exceptions import AuthError
from pprint import pprint
import time
import logging
from zipfile import ZipFile

load_dotenv()



def get_access_token(REFRESH_TOKEN):
    logging.debug(f"Requesting new access token using refresh token {REFRESH_TOKEN[-10:-1]}")
    res = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={"refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"},
        auth=(os.getenv("DROPBOX_APP_KEY"), os.getenv("DROPBOX_APP_SECRET")),
    )
    
    payload = {"token": res.json()["access_token"], "expires": time.time() + res.json()['expires_in'], "requested": time.time()}
    return payload


def get_folder_cursor(path, access_token):
    dbx = dropbox_connect(access_token)

    try:
        cursor = dbx.files_list_folder(path).cursor
        return {"cursor": cursor}
        

    except Exception as e:
        print("Error getting list of files from Dropbox: " + str(e))


def dropbox_connect(access_token):
    """Create a connection to Dropbox."""

    try:
        logging.debug(f"Attempting to connect to Dropbox API using access token {access_token[-10:-1]}")
        dbx = dropbox.Dropbox(access_token)
        logging.debug("Dropbox API connection successful")
    except AuthError as e:
        logging.error(f"Error connecting to Dropbox with access token {access_token[-10:-1]}. Error message:")
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

            # files_list

            has_more = response.has_more
            return {"cursor": response.cursor, "files_list": files_list, "entries":response.entries}
        
        except Exception as e:
            logging.error("Error getting list of files from Dropbox: " + str(e))
            break


def dropbox_list_files(path, access_token):
    """Return a Pandas dataframe of files in a given Dropbox folder path in the Apps directory."""

    dbx = dropbox_connect(access_token)

    try:
        files = dbx.files_list_folder(path).entries
        files_list = []
        for file in files:
            if isinstance(file, dropbox.files.FileMetadata):
                metadata = {
                    "filename": file.name,
                    "path": file.path_display,
                    "client_modified_at": file.client_modified,
                    "server_modified_at": file.server_modified,
                }
                files_list.append(metadata)

        return files_list

    except Exception as e:
        print("Error getting list of files from Dropbox: " + str(e))


def dropbox_download_file(dropbox_file_path, local_file_path, access_token):
    """Download a file from Dropbox to the local machine."""
    logging.info(f"Downloading file {dropbox_file_path} from Dropbox...")
    try:
        dbx = dropbox_connect(access_token)

        with open(local_file_path, "wb") as f:
            metadata, result = dbx.files_download(path=dropbox_file_path)
            f.write(result.content)
    except Exception as e:
        logging.error(f"Error downloading file {dropbox_file_path} from Dropbox: ")
        logging.error(e)

def zipfile(file, outputZIP="attachment.zip"):

    try:
        # os.chdir(outputZIP.split('/')[0])
        with ZipFile(outputZIP, "w") as zip:
            zip.write(file)

        logging.info("All files zipped successfully!")

    except Exception as e:
        os.chdir("..")

# Buffer size 50 GB
BUF = 1 * 1024 * 1024 * 1024

def file_split(file, output_directory, max_size):
    """Split file into pieces, every size is  MAX = 15*1024*1024 Byte"""
    chapters = 1
    uglybuf = ""
    with open(file, "rb") as src:
        while True:
            filename = f"{(os.path.splitext(file)[0])}.z0{chapters}".split('/')[-1]
            tgt = open(f'{os.path.join(output_directory, filename)}', "wb")
            logging.info(f"Writing {filename}...")
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