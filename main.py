import functions_framework
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from datetime import datetime
# Google Drive連携に必要
from google.auth import default as google_auth_default
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import gspread
import platform
import hashlib
from google.cloud import storage
import time
from bs4 import BeautifulSoup, Comment
import requests
import json

# providersから新しいスクリーンショット用関数をインポート
from providers import (
    alibaba_handler,
    anthropic_handler,
    anyscale_handler,
    aws_cloudprice,
    azure_handler,
    baseten_handler,
    civo_handler,
    coreweave_handler,
    cudocompute_handler,
    datacrunch_handler,
    fireworks_handler,
    fluidstack_handler,
    genesiscloud_handler,
    google_handler,
    groq_handler,
    hyperstack_handler,
    koyeb_handler,
    lambda_labs_handler,
    liquidweb_handler,
    modal_handler,
    neevcloud_handler,
    oblivus_handler,
    openai_handler,
    oracle_handler,
    runpod_handler,
    sakura_internet_handler,
    sambanova_handler,
    scaleway_handler,
    seeweb_handler,
    sesterce_handler,
    soroban_highreso_handler,
    tencentcloud_handler,
    together_handler,
    vast_ai_handler
)

# ===============================================================
# Webサイト変更監視用ターゲット (JSONファイルから読み込み)
# ===============================================================
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'monitoring_targets.json')
    
    with open(json_path, 'r', encoding='utf-8') as f:
        MONITORING_TARGETS = json.load(f)
    print("Successfully loaded monitoring targets from monitoring_targets.json")

except FileNotFoundError:
    print("WARNING: monitoring_targets.json not found. Change detection will be skipped.")
    MONITORING_TARGETS = {}
except Exception as e:
    print(f"ERROR: Failed to load monitoring_targets.json: {e}")
    MONITORING_TARGETS = {}
# ===============================================================

def send_slack_notification(message):
    """Secret ManagerからWebhook URLを取得し、Slackに通知を送る"""
    try:
        webhook_url = "https://sample.com"

        # Slackに送信するメッセージのペイロードを作成
        payload = {"text": message}

        # Webhook URLにPOSTリクエストを送信
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status() # エラーがあれば例外を発生させる
        print("Successfully sent notification to Slack.")

    except Exception as e:
        print(f"Failed to send Slack notification: {e}")

def upload_monitoring_screenshots(drive_service, local_files, parent_folder_id):
    """監視用スクリーンショットをプラットフォーム別のフォルダにアップロードする"""
    if not local_files:
        return

    print("\n--- Uploading monitoring screenshots to Google Drive ---")
    try:
        # 1. "MONITORING" フォルダを探すか、なければ作成
        query = f"'{parent_folder_id}' in parents and name='MONITORING' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        response = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)', supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = response.get('files', [])
        
        if not items:
            print("Creating 'MONITORING' folder...")
            folder_meta = {'name': 'MONITORING', 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_folder_id]}
            monitoring_folder = drive_service.files().create(body=folder_meta, fields='id', supportsAllDrives=True).execute()
            monitoring_folder_id = monitoring_folder.get('id')
        else:
            monitoring_folder_id = items[0].get('id')

        # 2. 各ファイルをプラットフォームごとのサブフォルダにアップロード
        for local_path in local_files:
            # ファイル名からプラットフォーム名とベース名を解析 (例: runpod_homepage_base.png)
            filename = os.path.basename(local_path)
            parts = filename.split('_')
            platform_name = parts[0]
            
            # プラットフォームごとのサブフォルダを探すか、なければ作成
            query = f"'{monitoring_folder_id}' in parents and name='{platform_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            response = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)', supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            items = response.get('files', [])

            if not items:
                print(f"Creating '{platform_name}' subfolder...")
                subfolder_meta = {'name': platform_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [monitoring_folder_id]}
                platform_folder = drive_service.files().create(body=subfolder_meta, fields='id', supportsAllDrives=True).execute()
                platform_folder_id = platform_folder.get('id')
            else:
                platform_folder_id = items[0].get('id')

            # ファイルをアップロード
            print(f"Uploading {filename} to '{platform_name}' folder...")
            media = MediaFileUpload(local_path, mimetype='image/png')
            file_meta = {'name': filename, 'parents': [platform_folder_id]}
            drive_service.files().create(body=file_meta, media_body=media, fields='id', supportsAllDrives=True).execute()
            
    except Exception as e:
        print(f"An error occurred during monitoring screenshot upload: {e}")
        import traceback
        traceback.print_exc()

def _clean_html_for_comparison(html_content: str) -> str:
    """
    比較のためにHTMLから不要なタグや動的要素を削除し、
    本文テキストのみを抽出して正規化する。
    """
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # <<< ここからが改善点 >>>
        # scriptとstyleタグを削除 (従来通り)
        for tag in soup(['script', 'style']):
            tag.decompose()
            
        # ページ情報やトラッキングに関わるmetaタグを削除
        for tag in soup.find_all('meta'):
            tag.decompose()

        # CSRFトークンなどが含まれがちな非表示のinputタグを削除
        for tag in soup.find_all('input', {'type': 'hidden'}):
            tag.decompose()

        # HTMLコメントを削除 (例: )
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        # <<< 改善点ここまで >>>
        
        # bodyタグのテキストのみを抽出
        if soup.body:
            return soup.body.get_text(separator=' ', strip=True)
        else:
            return soup.get_text(separator=' ', strip=True)
            
    except Exception as e:
        print(f"  -> Error during HTML cleaning: {e}")
        return html_content

def check_website_changes(driver, drive_service, targets):
    print("\n--- Starting Website Change Detection ---")
    storage_client = storage.Client()
    bucket_name = "gcs-bucket-for-html"
    bucket = storage_client.bucket(bucket_name)
    
    output_dir = "/tmp"
    new_screenshots = []
    notifications = []

    for platform, pages in targets.items():
        for page in pages:
            url, name = page['url'], page['name']
            print(f"Checking {platform} - {name} ({url})...")
            
            try:
                # 1. 今日のHTMLを取得
                driver.get(url)
                time.sleep(5)
                html_today_raw = driver.page_source

                # 2. GCSから昨日のHTMLを取得
                blob_path = f"{platform}/{name}.html"
                blob = bucket.blob(blob_path)
                html_yesterday_raw = ""
                if blob.exists():
                    html_yesterday_raw = blob.download_as_text()

                # 3. 両方のHTMLをクリーニングし、ハッシュ値を計算して比較
                content_today = _clean_html_for_comparison(html_today_raw)
                content_yesterday = _clean_html_for_comparison(html_yesterday_raw)

                hash_today = hashlib.sha256(content_today.encode('utf-8')).hexdigest()
                hash_yesterday = hashlib.sha256(content_yesterday.encode('utf-8')).hexdigest()

                if hash_yesterday != hash_today:
                    is_changed = True
                    is_first_run = not html_yesterday_raw
                else:
                    is_changed = False
                    is_first_run = False
                total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
                driver.set_window_size(1920, total_height)
                time.sleep(2)
                # 4. 変更検知 or 初回実行時の処理
                if is_first_run or is_changed:
                    # 1. 毎回ウィンドウサイズを標準にリセットする
                    print("  -> Resizing window to standard size before measurement...")
                    driver.set_window_size(1920, 1080)
                    time.sleep(2)

                    # 2. より堅牢な方法でページのフルハイトを取得
                    total_height = driver.execute_script(
                        "return Math.max( document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight );"
                    )
                    
                    # 3. 取得した高さにウィンドウサイズをセット
                    print(f"  -> Setting window height to {total_height}px for full screenshot.")
                    driver.set_window_size(1920, total_height)
                    time.sleep(2)

                    if is_first_run:
                        print(f"  -> First run for {platform} - {name}. Saving baseline.")
                        notifications.append(f"Baseline for {platform} {name} has been saved.")
                        filename = f"{platform}_{name}_base.png"
                    else: # is_changed == True
                        print(f"  -> CHANGE DETECTED for {platform} - {name}!")
                        notifications.append(f"Change detected on {platform} {name}: {url}")
                        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                        filename = f"{platform}_{name}_diff_{timestamp}.png"
                    
                    filepath = os.path.join(output_dir, filename)
                    driver.save_screenshot(filepath)
                    new_screenshots.append(filepath)

                else:
                    print(f"  -> No change detected.")

                # 変更があった場合、または初回実行時は今日のHTMLをGCSに保存
                if is_first_run or is_changed:
                    blob.upload_from_string(html_today_raw, content_type='text/html')

            except Exception as e:
                print(f"  -> Error checking {platform} - {name}: {e}")
    
    # 6. 新しく撮影したスクリーンショットをアップロード
    if new_screenshots:
        PARENT_DRIVE_FOLDER_ID = "1mA4YZ00FXIZ5aMeq15vagz1jtQbCDT1R" # 監視フォルダの親フォルダID
        upload_monitoring_screenshots(drive_service, new_screenshots, PARENT_DRIVE_FOLDER_ID)

    # 7. 通知処理（実装は別途）
    if notifications:
        print("\n--- Sending Change Notifications to Slack ---")

        # 通知メッセージを1つにまとめる
        full_message = "以下のWebサイトで変更を検知しました。\n" + "\n".join(notifications)

        # Slackに通知
        send_slack_notification(full_message)

    else:
        print("\nNo website changes to notify.")

def check_website_changes_local(driver, targets):
    """
    【ローカル検証用】GCSの代わりにローカルフォルダを使って変更検知を行う
    """
    print("\n--- Starting Website Change Detection (LOCAL TEST MODE) ---")
    local_storage_path = os.path.join(os.getcwd(), "tmp_local_test")
    os.makedirs(local_storage_path, exist_ok=True)
    print(f"Using local storage at: {local_storage_path}")

    for platform, pages in targets.items():
        for page in pages:
            url, name = page['url'], page['name']
            print(f"Checking {platform} - {name} ({url})...")
            
            try:
                driver.get(url)
                time.sleep(5)
                html_today_raw = driver.page_source

                # ローカルのHTMLファイルパスを定義
                platform_path = os.path.join(local_storage_path, platform)
                os.makedirs(platform_path, exist_ok=True)
                html_file_path = os.path.join(platform_path, f"{name}.html")

                # ローカルから昨日のHTMLを取得
                html_yesterday_raw = ""
                if os.path.exists(html_file_path):
                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        html_yesterday_raw = f.read()

                # ハッシュ値を比較
                content_today = _clean_html_for_comparison(html_today_raw)
                content_yesterday = _clean_html_for_comparison(html_yesterday_raw)
                hash_today = hashlib.sha256(content_today.encode('utf-8')).hexdigest()
                hash_yesterday = hashlib.sha256(content_yesterday.encode('utf-8')).hexdigest()

                is_changed = hash_yesterday != hash_today
                is_first_run = not html_yesterday_raw

                total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
                driver.set_window_size(1920, total_height)
                time.sleep(2)

                if is_first_run or is_changed:
                    # 1. ウィンドウサイズをリセット
                    driver.set_window_size(1920, 1080)
                    time.sleep(2)
                    # 2. ページのフルハイトを堅牢な方法で取得
                    total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
                    # 3. 取得した高さにウィンドウサイズをセット
                    driver.set_window_size(1920, total_height)
                    time.sleep(2)

                    if is_first_run:
                        print(f"  -> First run for {platform} - {name}. Saving baseline.")
                        filename = f"{platform}_{name}_base.png"
                    else: # is_changed == True
                        print(f"  -> CHANGE DETECTED for {platform} - {name}!")
                        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                        filename = f"{platform}_{name}_diff_{timestamp}.png"

                    filepath = os.path.join(platform_path, filename)
                    driver.save_screenshot(filepath)
                    print(f"  -> Screenshot saved to: {filepath}")

                else:
                    print(f"  -> No change detected.")
                
                if is_changed or is_first_run:
                    with open(html_file_path, 'w', encoding='utf-8') as f:
                        f.write(html_today_raw)
                    print(f"  -> HTML saved to: {html_file_path}")

            except Exception as e:
                print(f"  -> Error checking {platform} - {name}: {e}")

def upload_files_to_drive(local_files, parent_folder_id):
    try:
        print("Authenticating with Google Drive...")
        # Cloud Runの環境を自動で認識し、適切な認証情報を取得する
        creds, project = google_auth_default(scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        print("Authentication successful.")

        # 1. 今日の日付のフォルダ（例: "2025-08-08"）を作成
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # 同じ名前のフォルダが既にないか確認
        query = f"'{parent_folder_id}' in parents and name='{today_str}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        response = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)', 
            supportsAllDrives=True, 
            includeItemsFromAllDrives=True
        ).execute()
        items = response.get('files', [])

        if not items:
            print(f"Creating new folder for today: {today_str}")
            folder_metadata = {
                'name': today_str,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            folder = service.files().create(body=folder_metadata, fields='id', supportsAllDrives=True).execute()
            target_folder_id = folder.get('id')
        else:
            print(f"Using existing folder for today: {today_str}")
            target_folder_id = items[0].get('id')
            
        # 2. スクリーンショットをアップロード
        for file_path in local_files:
            # 万が一、リストにNoneが混入していてもスキップする
            if not file_path:
                print("Skipping an invalid (None) file path.")
                continue
            
            file_name = os.path.basename(file_path)
            print(f"Uploading {file_name} to Google Drive...")
            media = MediaFileUpload(file_path, mimetype='image/png')
            file_metadata = {
                'name': file_name,
                'parents': [target_folder_id]
            }
            service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        
        print("All files uploaded successfully.")
        return True

    except Exception as e:
        # エラーの詳細を出力するためにTracebackを追加
        import traceback
        print(f"An error occurred during Google Drive upload: {e}")
        traceback.print_exc()
        return False

def save_data_to_spreadsheet(all_data, sheet_url, worksheet_name):
    """
    取得した価格データのリストを、指定されたGoogleスプレッドシートに書き込む
    """
    try:
        print("Authenticating with Google Sheets...")
        # Cloud Runの環境を自動で認識し、認証情報を取得
        creds, project = google_auth_default(scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ])
        gc = gspread.authorize(creds)
        
        spreadsheet = gc.open_by_url(sheet_url)
        
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            # シートが存在しない場合は新規作成
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="1000", cols="20")

        print(f"Successfully connected to worksheet: '{worksheet_name}'")

        # --- データの整形 ---
        header = ['Date', 'Company', 'Variation', 'Region', 'GPU_Type', 'API_TYPE', 'Size', 'Price']
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        rows_to_append = []
        for data_dict in all_data:
            is_api_data = data_dict.get("API_TYPE") and data_dict["API_TYPE"] != "N/A"
            # runpod_handlerから取得した辞書のキーを、スプレッドシートのカラムにマッピング
            if is_api_data:
                # APIデータの場合の行を作成
                row = [
                    today_str,
                    data_dict.get("Provider Name", "N/A"),
                    data_dict.get("GPU Variant Name", "N/A"), # APIではN/A
                    data_dict.get("Region", "N/A"),
                    "", # GPU_Type は空
                    data_dict.get("API_TYPE", "N/A"), # API_TYPE を設定
                    data_dict.get("Period", "N/A"), # "Per 1M Tokens" など
                    data_dict.get("Total Price ($)", "N/A")
                ]
            else:
                row = [
                    today_str,
                    data_dict.get("Provider Name", "N/A"),
                    data_dict.get("GPU Variant Name", "N/A"),
                    data_dict.get("Region", "N/A"),
                    data_dict.get("GPU (H100 or H200 or L40S)", "N/A"),
                    "", # API_TYPE は空
                    f'{data_dict.get("Number of Chips", "N/A")}x',
                    data_dict.get("Total Price ($)", "N/A")
                ]
            rows_to_append.append(row)
        
        # --- 書き込み処理 ---
        # シートが空の場合、最初にヘッダーを書き込む
        if not worksheet.get_all_values():
            print("Worksheet is empty. Writing header.")
            worksheet.append_row(header)
        
        if rows_to_append:
            print(f"Appending {len(rows_to_append)} rows to the worksheet...")
            worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            print("Successfully saved data to spreadsheet.")
        else:
            print("No data to save.")

    except Exception as e:
        import traceback
        print(f"An error occurred during Google Sheets operation: {e}")
        traceback.print_exc()

@functions_framework.http
def screenshot_entry_point(request):

    all_handlers = [
        alibaba_handler, runpod_handler, anyscale_handler, civo_handler, cudocompute_handler,
        coreweave_handler, fluidstack_handler, genesiscloud_handler, koyeb_handler, lambda_labs_handler,
        hyperstack_handler, liquidweb_handler, modal_handler, neevcloud_handler, oblivus_handler, vast_ai_handler,
        datacrunch_handler, sakura_internet_handler, scaleway_handler, seeweb_handler, sesterce_handler, soroban_highreso_handler,
        anthropic_handler, aws_cloudprice, azure_handler, baseten_handler, fireworks_handler, google_handler, groq_handler,
        openai_handler, oracle_handler, sambanova_handler, tencentcloud_handler, together_handler
    ]
    done = [
        alibaba_handler, runpod_handler
    ]
    # 1. ブラウザを起動する
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # メモリ不足対策
    options.add_argument("window-size=1920,1080") # ウィンドウサイズ指定
    # 一般的なユーザーエージェントを設定してbot検出を避ける
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36')
    
    if platform.system() == "Linux":
        # クラウド環境 (Linux) の場合、パスを明示的に指定
        print("Running in Linux environment (Cloud Run). Setting explicit paths.")
        options.binary_location = "/usr/bin/google-chrome"
        service = Service(executable_path="/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    else:
        print("Running in local environment (Windows/Mac). Using automatic driver management.")
        driver = webdriver.Chrome(options=options)
    
    output_dir = "/tmp" # 保存先
    saved_files = [] # 保存したファイルパスを記録するリスト
    all_scraped_data = []

    # 2. 各ハンドラを呼び出し、ブラウザの操作権を渡す
    print("--- Processing ---")
    for handler in all_handlers:
        handler_name = handler.__name__.split('.')[-1]
        print(f"--- Processing {handler_name} ---")
        
        try:
            screenshot_paths, scraped_data = handler.process_data_and_screenshot(driver, output_dir)

            if screenshot_paths:
                saved_files.extend(screenshot_paths)
                print(f"  -> Got {len(screenshot_paths)} screenshot(s) from {handler_name}.")
            
            if scraped_data:
                all_scraped_data.extend(scraped_data)
                print(f"  -> Got {len(scraped_data)} data rows from {handler_name}.")

        except Exception as e:
            # ハンドラ実行中に予期せぬエラーが起きた場合
            print(f"!!! An unexpected error occurred in {handler_name}: {e}. Skipping.")

    # Google Drive/GCSへの接続情報を再利用するために先に定義
    try:
        creds, project = google_auth_default(scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/devstorage.read_write' # GCSのスコープを追加
        ])
        drive_service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"Failed to authenticate with Google services: {e}")
        driver.quit()
        return "Authentication failed.", 500

    # === Webサイト変更監視処理 ===
    if MONITORING_TARGETS:
        # check_website_changes(driver, drive_service, MONITORING_TARGETS)
        check_website_changes_local(driver, MONITORING_TARGETS)

    # 3. ブラウザを閉じる
    driver.quit()

    if saved_files:
        print(f"\nAll screenshots taken. Uploading {len(saved_files)} files to Google Drive...")
        PARENT_FOLDER_ID = "1mA4YZ00FXIZ5aMeq15vagz1jtQbCDT1R"
        # upload_files_to_drive(saved_files, PARENT_FOLDER_ID)

    if all_scraped_data:
        print(f"\nSaving {len(all_scraped_data)} rows of pricing data to Google Sheets...")
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1LHxboVJ_YXMmLOsEBFPQYrzRQx629p33_JqS0xuzW24/edit?gid=0#gid=0"
        WORKSHEET_NAME = "シート1"
        save_data_to_spreadsheet(all_scraped_data, SHEET_URL, WORKSHEET_NAME)

    return "Screenshot process completed.", 200

if __name__ == "__main__":
    # ローカル実行用の設定
    print("Running in local mode...")
    screenshot_entry_point(None)