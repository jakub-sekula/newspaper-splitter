# MAX = 500*1024*1024    # 500Mb    - max chapter size
MAX = 1 * 1024 * 1024
BUF = 50 * 1024 * 1024 * 1024  # 50GB     - memory buffer size

import os
from zipfile import ZipFile


def file_split(file, output_directory, max_size):
    """Split file into pieces, every size is  MAX = 15*1024*1024 Byte"""
    chapters = 1
    uglybuf = ""
    with open(file, "rb") as src:
        while True:
            filename = f"{(os.path.splitext(file)[0])}.z0{chapters}".split('/')[-1]
            print(filename)

            tgt = open(f'{os.path.join(output_directory, filename)}', "wb")
            print(f"Writing {filename}...")
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
            print(f"Written {filename}!")
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


def zipfile(file, outputZIP="attachment.zip"):
    # path to folder which needs to be zipped
    # directory = './outbox'

    # calling function to get all file paths in the directory
    with ZipFile(outputZIP, "w") as zip:
        # writing each file one by one
        zip.write(file)

    print("All files zipped successfully!")

# if __name__ == "__main__":
#     outputZIP = 'Gazeta Wyborcza 20221022Szczecin.mobi.zip'
#     zipfiles("./gazetka", outputZIP)
#     file_split(outputZIP, MAX)
