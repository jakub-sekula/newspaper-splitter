from dotenv import load_dotenv
import os
import requests
import dropbox
from dropbox.exceptions import AuthError
from pprint import pprint

load_dotenv()

def get_access_token(REFRESH_TOKEN):
    res = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={"refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"},
        auth=(os.getenv("DROPBOX_APP_KEY"), os.getenv("DROPBOX_APP_SECRET")),
    )

    return res.json()["access_token"]


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
        dbx = dropbox.Dropbox(access_token)
    except AuthError as e:
        print("Error connecting to Dropbox with access token: " + str(e))
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
            print("Error getting list of files from Dropbox: " + str(e))
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

    try:
        dbx = dropbox_connect(access_token)

        with open(local_file_path, "wb") as f:
            metadata, result = dbx.files_download(path=dropbox_file_path)
            f.write(result.content)
    except Exception as e:
        print("Error downloading file from Dropbox: " + str(e))