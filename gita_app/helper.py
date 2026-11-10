from pathlib import Path
import json, os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
from auth.admin import get_drive_service, get_files_drive

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()
FOLDER_ID = "11yhz_aFxzjlTHuN1ob85eySdmNEI0fSD"
KEY_FILE = json.loads(os.getenv('GOOGLE_OAUTH_CREDENTIALS_JSON'))
SCOPES = ["https://www.googleapis.com/auth/drive"]

def upload_to_drive():
    drive_files = get_files_drive()
    json_folder = os.path.join(BASE_DIR, "static", "json_files")
    files = os.listdir(json_folder)
    file_list = []
    for file in files:
        if not any(file in v.values() for v in drive_files):
            file_list.append(file)
    if len(file_list) == 0:
        print("No files in folder")
        return None
    drive = get_drive_service()
    for file_name in file_list:
        file_path = os.path.join(BASE_DIR, "static", "json_files", file_name)
        json_file = Path(file_path)
        # Upload one JSON file into the folder.
        metadata = {
            "name": json_file.name,
            "mimeType": "application/json",
            "parents": [FOLDER_ID],
        }
        uploaded = drive.files().create(
            body=metadata,
            media_body=MediaFileUpload(
                str(json_file),
                mimetype="application/json",
                resumable=True,
            ),
            fields="id,name",
        ).execute()
        print("Uploaded:", uploaded["name"], uploaded["id"])
    return True


if __name__ == "__main__":
    # /home/KrishaTeach/gitaapp/gita_app/auth/json using codes/acharya_translations_cache.json
    # upload_to_drive()
    drive, res = get_drive_service()
    if drive:
        print(get_files_drive(drive),res)
    else:
        print(res)



