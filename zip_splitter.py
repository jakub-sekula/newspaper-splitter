# MAX = 500*1024*1024    # 500Mb    - max chapter size
MAX = 2 * 1024 * 1024
BUF = 50 * 1024 * 1024 * 1024  # 50GB     - memory buffer size

import os
from zipfile import ZipFile


def file_split(FILE, MAX):
    """Split file into pieces, every size is  MAX = 15*1024*1024 Byte"""
    chapters = 1
    uglybuf = ""
    with open(FILE, "rb") as src:
        while True:
            tgt = open(f'{os.path.splitext(FILE)[0]}.z0{chapters}', "wb")
            written = 0
            while written < MAX:
                if len(uglybuf) > 0:
                    tgt.write(uglybuf)
                tgt.write(src.read(min(BUF, MAX - written)))
                written += min(BUF, MAX - written)
                uglybuf = src.read(1)
                if len(uglybuf) == 0:
                    break
            tgt.close()
            if len(uglybuf) == 0:
                break
            chapters += 1


def get_all_file_paths(directory):
    return os.listdir(directory)


def zipfiles(directory, outputZIP="attachment.zip"):
    # path to folder which needs to be zipped
    # directory = './outbox'

    # calling function to get all file paths in the directory
    file_paths = get_all_file_paths(directory)

    # printing the list of all files to be zipped
    print("Following files will be zipped:")
    for file_name in file_paths:
        print(file_name)

    os.chdir(directory)

    # writing files to a zipfile
    with ZipFile(outputZIP, "w") as zip:
        # writing each file one by one
        for file in file_paths:
            zip.write(file)

    print("All files zipped successfully!")


if __name__ == "__main__":
    outputZIP = f'{os.path.splitext(os.listdir("./gazetka")[1])[0]}.zip'
    zipfiles("./gazetka", outputZIP)
    file_split(outputZIP, MAX)
