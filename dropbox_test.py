# import flask
import os
from pprint import pprint
import pathlib
from dotenv import load_dotenv

load_dotenv()

from utils import (
    dropbox_download_file,
    dropbox_list_files,
)

from zip_splitter import zipfile, file_split
from mailer_test import send_mail

file_list = dropbox_list_files(os.getenv("DROPBOX_FOLDER_PATH"))

# pprint(file_list)

file_path = file_list[-1]["path"]
file_name = file_list[-1]["filename"]

dropbox_download_file(file_path, file_name)

outputZIP = f'./zips/{file_name}.zip'
zipfile(file_name, outputZIP)
file_split(outputZIP, 1 * 1024 * 1024)

os.chdir('zips')

kek = filter(lambda x:os.path.splitext(x)[1] != '.zip' and x[0] != ".", os.listdir())


for x in kek:
    print(f'Sending {x}...')
    send_mail(x)