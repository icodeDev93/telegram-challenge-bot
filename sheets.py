import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io
import requests
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class SheetsClient:
    def __init__(self, sheet_id, creds_path, folder_id):
	creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_file(creds_dict, scopes=SCOPES)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(sheet_id)
        self.drive_service = build("drive", "v3", credentials=creds)
        self.folder_id = folder_id

    # read current week number from Settings sheet (cell A2)
    def get_current_week(self):
        ws = self.sheet.worksheet("Settings")
        val = ws.acell("A2").value
        return int(val) if val and val.isdigit() else None

    def upload_photo_to_drive(self, file_bytes: bytes, filename: str) -> str:
        """
        Upload bytes to Drive (under self.folder_id), make file 'anyone with link' reader,
        and return a browser-friendly view URL.
        """
        from googleapiclient.http import MediaIoBaseUpload
        import io, time

        # Prepare media and metadata
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="image/jpeg", resumable=True)
        file_metadata = {
            "name": filename,
        }
        if self.folder_id:
            file_metadata["parents"] = [self.folder_id]

        # Create the file on Drive (supportsAllDrives=True for Shared Drives)
        created = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink",
            supportsAllDrives=True
        ).execute()

        file_id = created.get("id")

        # Create an 'anyone with link' permission so the link is viewable in browser
        try:
            self.drive_service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            # log but continue; sometimes permission creation requires special roles
            print(f"[SheetsClient] Warning: permission creation failed: {e}")

        # Try to return a friendly view link. webViewLink is ideal; fall back to a direct viewer URL.
        web_view = created.get("webViewLink") or created.get("webContentLink")
        if web_view:
            return web_view

        # Fallback: construct view URL from file id
        return f"https://drive.google.com/file/d/{file_id}/view"


    # insert a submission into Main sheet
    def insert_main_submission(self, user_id, username, week_number, answer, score=""):
        ws = self.sheet.worksheet("Main")
        row = [
            str(user_id),
            username,
            datetime.utcnow().isoformat(),
            str(week_number),
            answer,
            str(score)
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    # read leaderboard data
    def _read_leaderboard_table(self):
        try:
            ws = self.sheet.worksheet("Leaderboard & Points")
        except Exception:
            return []

        rows = ws.get_all_values()
        if not rows or len(rows) < 2:
            return []
        header = rows[0]
        data_rows = rows[1:]
        records = []
        for r in data_rows:
            rec = {}
            for i, h in enumerate(header):
                rec[h] = r[i] if i < len(r) else ""
            records.append(rec)
        return records

    # fetch top N leaderboard
    def get_leaderboard_top(self, n=10):
        recs = self._read_leaderboard_table()
        safe_recs = []
        for r in recs:
            raw = r.get("total_points", "") or ""
            raw_str = str(raw).strip().replace(",", "")
            try:
                pts = float(raw_str) if raw_str != "" else 0.0
            except Exception:
                pts = 0.0
            r["total_points"] = pts
            safe_recs.append(r)

        recs_sorted = sorted(safe_recs, key=lambda x: x["total_points"], reverse=True)
        return recs_sorted[:n]

    # get user’s points and rank
    def get_user_points_and_rank(self, user_id):
        ws = self.sheet.worksheet("Leaderboard & Points")
        data = ws.get_all_records()
        for r in data:
            if str(r.get("user_id")) == str(user_id):
                return r.get("total_points"), r.get("rank")
        return 0, None
