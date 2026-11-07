from pathlib import Path
import json, os
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()
FOLDER_ID = "11yhz_aFxzjlTHuN1ob85eySdmNEI0fSD"
KEY_FILE = json.loads(os.getenv('GOOGLE_OAUTH_CREDENTIALS_JSON'))
SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    creds = None
    if os.path.exists("credentials/token.json"):
        creds = Credentials.from_authorized_user_file("credentials/token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            KEY_FILE, SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open("credentials/token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

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

def get_files_drive():
    drive = get_drive_service()
    # List JSON files in the folder, handling pagination.
    query = f"'{FOLDER_ID}' in parents and trashed = false"
    json_files = []
    page_token = None

    while True:
        result = drive.files().list(
            q=query,
            pageSize=1000,
            pageToken=page_token,
            fields="nextPageToken,files(id,name,mimeType)",
        ).execute()

        json_files.extend(
            f for f in result.get("files", [])
            if f["name"].lower().endswith(".json")
            or f["mimeType"] == "application/json"
        )

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print("JSON files in folder:")
    for item in json_files:
        print(item["id"], item["name"])
    return json_files

if __name__ == "__main__":
    # /home/KrishaTeach/gitaapp/gita_app/auth/json using codes/acharya_translations_cache.json
    # upload_to_drive()
    get_files_drive()


