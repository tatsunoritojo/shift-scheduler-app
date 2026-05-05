"""
Onedrop パイロット導入 進捗管理スプレッドシートを作成するスクリプト。
tatsunoritojo@gmail.com の Google Drive に作成される。

Usage:
    python scripts/create_pilot_spreadsheet.py

ブラウザが開くので tatsunoritojo@gmail.com でログインして承認してください。
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]

STAFF_COUNT = 12

# Color definitions (RGB 0-1)
COLORS = {
    "header_bg": {"red": 0.16, "green": 0.38, "blue": 0.60},       # Dark blue
    "header_text": {"red": 1, "green": 1, "blue": 1},              # White
    "name_col_bg": {"red": 0.93, "green": 0.95, "blue": 0.98},     # Light blue
    "gmail_col_bg": {"red": 1, "green": 1, "blue": 0.90},          # Light yellow (input area)
    "status_col_bg": {"red": 0.95, "green": 0.95, "blue": 0.95},   # Light gray
    "notes_col_bg": {"red": 1, "green": 1, "blue": 1},             # White
    "done_green": {"red": 0.85, "green": 0.95, "blue": 0.85},      # Green for ✓
    "not_done_red": {"red": 1, "green": 0.90, "blue": 0.90},       # Red for -
    "border": {"red": 0.75, "green": 0.75, "blue": 0.75},          # Gray border
}


def get_credentials():
    """OAuth flow — opens browser for authorization."""
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    return creds


def create_spreadsheet(service):
    """Create the spreadsheet with a single sheet."""
    body = {
        "properties": {
            "title": "Shifree導入 進捗管理（4/6〜5/3シフト）",
            "locale": "ja_JP",
        },
        "sheets": [
            {
                "properties": {
                    "title": "進捗管理",
                    "gridProperties": {"rowCount": STAFF_COUNT + 3, "columnCount": 8},
                }
            }
        ],
    }
    spreadsheet = service.spreadsheets().create(body=body).execute()
    return spreadsheet["spreadsheetId"], spreadsheet["sheets"][0]["properties"]["sheetId"]


def build_requests(sheet_id):
    """Build all formatting/validation requests."""
    requests = []

    # --- Column widths ---
    col_widths = [40, 120, 250, 90, 90, 100, 100, 200]
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # --- Row height for header ---
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 40},
            "fields": "pixelSize",
        }
    })

    # --- Header formatting ---
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 8},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLORS["header_bg"],
                    "textFormat": {"foregroundColor": COLORS["header_text"], "bold": True, "fontSize": 11},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat",
        }
    })

    # --- Data area: column-specific backgrounds ---
    data_start = 1
    data_end = STAFF_COUNT + 1

    # Column A (#): light blue
    col_bgs = [
        (0, 1, COLORS["name_col_bg"]),    # #
        (1, 2, COLORS["name_col_bg"]),    # 名前
        (2, 3, COLORS["gmail_col_bg"]),   # Gmail (input)
        (3, 4, COLORS["status_col_bg"]),  # GCP登録
        (4, 5, COLORS["status_col_bg"]),  # 招待送信
        (5, 6, COLORS["status_col_bg"]),  # ログイン済
        (6, 7, COLORS["status_col_bg"]),  # シフト提出
        (7, 8, COLORS["notes_col_bg"]),   # 備考
    ]
    for start_col, end_col, color in col_bgs:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": start_col, "endColumnIndex": end_col},
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    # --- Center align status columns + # column ---
    for col_start, col_end in [(0, 1), (3, 7)]:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": col_start, "endColumnIndex": col_end},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment",
            }
        })

    # --- Dropdown validation for status columns (D-G: columns 3-6) ---
    for col in range(3, 7):
        requests.append({
            "setDataValidation": {
                "range": {"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": col, "endColumnIndex": col + 1},
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "✓"},
                            {"userEnteredValue": "—"},
                        ],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        })

    # --- Conditional formatting: green for ✓ ---
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 3, "endColumnIndex": 7}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "✓"}]},
                    "format": {"backgroundColor": COLORS["done_green"]},
                },
            },
            "index": 0,
        }
    })

    # --- Conditional formatting: red for — ---
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 3, "endColumnIndex": 7}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "—"}]},
                    "format": {"backgroundColor": COLORS["not_done_red"]},
                },
            },
            "index": 1,
        }
    })

    # --- Borders for entire data area ---
    requests.append({
        "updateBorders": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": data_end, "startColumnIndex": 0, "endColumnIndex": 8},
            "top": {"style": "SOLID", "color": COLORS["border"]},
            "bottom": {"style": "SOLID", "color": COLORS["border"]},
            "left": {"style": "SOLID", "color": COLORS["border"]},
            "right": {"style": "SOLID", "color": COLORS["border"]},
            "innerHorizontal": {"style": "SOLID", "color": COLORS["border"]},
            "innerVertical": {"style": "SOLID", "color": COLORS["border"]},
        }
    })

    # --- Freeze header row ---
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # --- Protect columns D-G (admin-only: GCP登録〜シフト提出) ---
    requests.append({
        "addProtectedRange": {
            "protectedRange": {
                "range": {"sheetId": sheet_id, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 3, "endColumnIndex": 7},
                "description": "管理者のみ編集可（GCP登録〜シフト提出）",
                "warningOnly": True,
            }
        }
    })

    return requests


def populate_data(service, spreadsheet_id):
    """Write headers and row numbers."""
    headers = [["#", "名前", "Googleアカウント (Gmail)", "GCP登録", "招待送信", "ログイン済", "シフト提出", "備考"]]
    rows = [[i, "", "", "—", "—", "—", "—", ""] for i in range(1, STAFF_COUNT + 1)]

    # Summary row
    summary_row = [["", "", "記入率", '=COUNTIF(C2:C13,"<>")/12*100&"%"',
                    "", "", '=COUNTIF(G2:G13,"✓")&"/12"', ""]]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="進捗管理!A1:H1",
        valueInputOption="RAW",
        body={"values": headers},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="進捗管理!A2:H13",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="進捗管理!A14:H14",
        valueInputOption="USER_ENTERED",
        body={"values": summary_row},
    ).execute()


def main():
    print("ブラウザが開きます。tatsunoritojo@gmail.com でログインしてください。")
    creds = get_credentials()

    service = build("sheets", "v4", credentials=creds)

    print("スプレッドシートを作成中...")
    spreadsheet_id, sheet_id = create_spreadsheet(service)

    print("フォーマット設定中...")
    requests = build_requests(sheet_id)
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()

    print("データ入力中...")
    populate_data(service, spreadsheet_id)

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    print(f"\n✅ 作成完了!")
    print(f"URL: {url}")
    print(f"\n次のステップ:")
    print(f"  1. 上記URLを開いて内容を確認")
    print(f"  2. 共有設定で「リンクを知っている全員が編集可」に変更")
    print(f"  3. LINEグループにURLを投稿")


if __name__ == "__main__":
    main()
