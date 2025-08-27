import functions_framework
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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
from PIL import Image
import google.generativeai as genai
from google.cloud import aiplatform
from dotenv import load_dotenv
import os

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

load_dotenv()

def summarize_with_gemini(title: str, description: str, project_id: str, location: str) -> str:
    """Gemini APIを使って、ブログタイトルから内容の要約を生成する"""
    print(f"  -> Summarizing title with Gemini: '{title}'")
    prompt = (
        "あなたはIT分野の専門家です。以下のブログ記事のタイトルと概要から、"
        "どのような内容の記事か、技術者向けに簡潔な日本語で3行の要約を生成してください。\n\n"
        f"【タイトル】\n{title}\n\n"
        f"【概要】\n{description}"
    )

    try:
        # GCP環境（Cloud Runなど）で実行されているか判定
        if os.getenv('K_SERVICE'):
            print("  -> Using Vertex AI (production mode)")
            aiplatform.init(project=project_id, location=location)
            model = genai.GenerativeModel("gemini-1.5-flash-001")
            response = model.generate_content(prompt)
            return response.text.strip()
        else:
            print("  -> Using Google AI Studio API Key (local mode)")
            # ローカル実行時は環境変数からAPIキーを読み込む
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                return "Error: GEMINI_API_KEY environment variable not set for local execution."
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
            response = model.generate_content(prompt)
            return response.text.strip()

    except Exception as e:
        print(f"  -> Gemini API call failed: {e}")
        return f"Error summarizing title: {e}"

def take_scrolling_screenshot(driver, filepath):
    """
    ページをスクロールしながら複数のスクリーンショットを撮影し、1枚の画像に結合する。
    """
    print("  -> Taking scrolling screenshot...")
    try:
        driver.set_window_size(1920, 800) # まずは標準的なサイズに
        time.sleep(1)
        
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        # 結合用の元となる空の画像を作成
        stitched_image = Image.new('RGB', (1920, total_height))
        
        scroll_position = 0
        while scroll_position < total_height:
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(0.5) # スクロール後の描画を待つ
            
            # 一時ファイルとしてスクリーンショットを撮影
            temp_screenshot_path = os.path.join(os.path.dirname(filepath), "temp_screenshot.png")
            driver.save_screenshot(temp_screenshot_path)
            
            screenshot_part = Image.open(temp_screenshot_path)
            
            # 撮影した部分を結合用画像に貼り付け
            stitched_image.paste(screenshot_part, (0, scroll_position))
            
            scroll_position += viewport_height

        # 結合した画像を保存
        stitched_image.save(filepath)
        print(f"  -> Scrolling screenshot saved to: {filepath}")
        
        # 一時ファイルを削除
        if os.path.exists(temp_screenshot_path):
            os.remove(temp_screenshot_path)
            
        return True
    except Exception as e:
        print(f"  -> Failed to take scrolling screenshot: {e}")
        # 失敗した場合は、見える範囲だけでも撮影しておく
        driver.save_screenshot(filepath)
        return False

def execute_pre_action(driver, action_name):
    """
    指定された名前のアクションを実行する
    """
    print(f"  -> Executing pre-action: {action_name}")
    if action_name == "click_cudo_cookie_decline":
        try:
            wait = WebDriverWait(driver, 10)
            decline_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Decline optional cookies')]"))
            )
            decline_button.click()
            time.sleep(2) # ポップアップが消えるのを待つ
            print("  -> Successfully clicked Cudo cookie decline button.")
        except TimeoutException:
            print("  -> Cudo cookie pop-up not found. Proceeding anyway.")

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
        webhook_url = "https://hooks.slack.com/services/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"

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
    gcp_project_id = "your-gcp-project-id"
    gcp_location = "asia-northeast1"
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

                if pre_action := page.get("pre_action"):
                    execute_pre_action(driver, pre_action)

                check_type = page.get("check_type", "hash") # デフォルトはhash

                if check_type == "latest_title":
                    # --- 新しい：最新タイトルの比較ロジック ---
                    selectors = page.get("selectors")
                    if not selectors or "title" not in selectors or "description" not in selectors:
                        print("  -> ERROR: 'latest_title' check type requires 'selectors' with 'title' and 'description'. Skipping.")
                        continue

                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    title_elem = soup.select_one(selectors["title"])
                    desc_elem = soup.select_one(selectors["description"])

                    if not title_elem or not desc_elem:
                        print("  -> ERROR: Could not find title or description element with the given selectors. Skipping.")
                        continue

                    latest_title = title_elem.get_text(strip=True)
                    latest_desc = desc_elem.get_text(strip=True)
                    current_content = f"TITLE: {latest_title}\nDESC: {latest_desc}"
                    
                    # 前回の内容をローカルファイルから取得
                    content_file_path = os.path.join(output_dir, f"{name}_content.txt")
                    previous_content = ""
                    if os.path.exists(content_file_path):
                        with open(content_file_path, 'r', encoding='utf-8') as f:
                            previous_content = f.read()

                    is_changed = previous_content != current_content
                    is_first_run = not previous_content

                    if is_first_run or is_changed:
                        if is_first_run:
                            print(f"  -> First run for {platform} - {name}. Saving baseline title.")
                        else:
                            print(f"  -> NEW BLOG POST DETECTED! Title: {latest_title}")
                            summary = summarize_with_gemini(latest_title, latest_desc, gcp_project_id, gcp_location)
                            slack_message = (
                                f"【ブログ更新検知】\n"
                                f"プラットフォーム: {platform}\n"
                                f"ページ: {name} ({url})\n"
                                f"新タイトル: {latest_title}\n\n"
                                f"▼ Geminiによる内容予測:\n{summary}"
                            )
                            notifications.append(slack_message)
                        
                        # スクリーンショット撮影と内容の保存
                        filename = f"{platform}_{name}_base.png" if is_first_run else f"{platform}_{name}_diff_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
                        filepath = os.path.join(output_dir, filename)
                        take_scrolling_screenshot(driver, filepath)

                        with open(content_file_path, 'w', encoding='utf-8') as f:
                            f.write(current_content)
                        print(f"  -> Content saved to: {content_file_path}")
                    else:
                        print("  -> No new blog post detected.")

                else:
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
                        filename = ""
                        if is_first_run:
                            print(f"  -> First run for {platform} - {name}. Saving baseline.")
                            filename = f"{platform}_{name}_base.png"
                            notifications.append(f"Local test - Baseline for {platform} {name} has been saved.")
                        elif is_changed:
                            print(f"  -> CHANGE DETECTED for {platform} - {name}!")
                            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                            filename = f"{platform}_{name}_diff_{timestamp}.png"
                            notifications.append(f"Local test - Change detected on {platform} {name}: {url}")
                        
                        if filename:
                            filepath = os.path.join(output_dir, filename)
                            # <<< 従来の撮影方法から新しい関数呼び出しに変更 >>>
                            take_scrolling_screenshot(driver, filepath)

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
    notifications = []
    
    # ローカル実行時のためのダミー情報
    gcp_project_id = "your-gcp-project-id"
    gcp_location = "asia-northeast1"

    for platform, pages in targets.items():
        for page in pages:
            url, name = page['url'], page['name']
            print(f"Checking {platform} - {name} ({url})...")
            
            try:
                driver.get(url)
                time.sleep(5)

                if pre_action := page.get("pre_action"):
                    execute_pre_action(driver, pre_action)
                
                check_type = page.get("check_type", "hash")
                
                platform_path = os.path.join(local_storage_path, platform)
                os.makedirs(platform_path, exist_ok=True)

                # --- 監視タイプに応じて処理を分岐 ---
                if check_type == "latest_title":
                    # <<< 新しいロジック：最新タイトルと概要の比較 >>>
                    selectors = page.get("selectors")
                    if not selectors or "title" not in selectors or "description" not in selectors:
                        print("  -> ERROR: 'latest_title' check type requires 'selectors' with 'title' and 'description'. Skipping.")
                        continue

                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    title_elem = soup.select_one(selectors["title"])
                    desc_elem = soup.select_one(selectors["description"])

                    if not title_elem or not desc_elem:
                        print("  -> ERROR: Could not find title or description element with the given selectors. Skipping.")
                        continue

                    latest_title = title_elem.get_text(strip=True)
                    latest_desc = desc_elem.get_text(strip=True)
                    current_content = f"TITLE: {latest_title}\nDESC: {latest_desc}"
                    
                    # 前回の内容をローカルファイルから取得
                    content_file_path = os.path.join(platform_path, f"{name}_content.txt")
                    previous_content = ""
                    if os.path.exists(content_file_path):
                        with open(content_file_path, 'r', encoding='utf-8') as f:
                            previous_content = f.read()

                    is_changed = previous_content != current_content
                    is_first_run = not previous_content

                    if is_first_run or is_changed:
                        if is_first_run:
                            print(f"  -> First run for {platform} - {name}. Saving baseline title.")
                            summary = summarize_with_gemini(latest_title, latest_desc, gcp_project_id, gcp_location)
                            slack_message = (
                                f"【ブログ更新検知】\n"
                                f"プラットフォーム: {platform}\n"
                                f"ページ: {name} ({url})\n"
                                f"新タイトル: {latest_title}\n\n"
                                f"▼ Geminiによる内容予測:\n{summary}"
                            )
                            notifications.append(slack_message)
                            print(slack_message)
                        else:
                            print(f"  -> NEW BLOG POST DETECTED! Title: {latest_title}")
                            summary = summarize_with_gemini(latest_title, latest_desc, gcp_project_id, gcp_location)
                            slack_message = (
                                f"【ブログ更新検知】\n"
                                f"プラットフォーム: {platform}\n"
                                f"ページ: {name} ({url})\n"
                                f"新タイトル: {latest_title}\n\n"
                                f"▼ Geminiによる内容予測:\n{summary}"
                            )
                            notifications.append(slack_message)
                            print(slack_message)
                        
                        # スクリーンショット撮影と内容の保存
                        filename = f"{platform}_{name}_base.png" if is_first_run else f"{platform}_{name}_diff_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
                        filepath = os.path.join(platform_path, filename)
                        take_scrolling_screenshot(driver, filepath)

                        with open(content_file_path, 'w', encoding='utf-8') as f:
                            f.write(current_content)
                        print(f"  -> Content saved to: {content_file_path}")
                    else:
                        print("  -> No new blog post detected.")

                else: # check_type == "hash"
                    html_today_raw = driver.page_source
                    html_file_path = os.path.join(platform_path, f"{name}.html")
                    html_yesterday_raw = ""
                    if os.path.exists(html_file_path):
                        with open(html_file_path, 'r', encoding='utf-8') as f:
                            html_yesterday_raw = f.read()

                    content_today = _clean_html_for_comparison(html_today_raw, page.get("selector"))
                    content_yesterday = _clean_html_for_comparison(html_yesterday_raw, page.get("selector"))
                    hash_today = hashlib.sha256(content_today.encode('utf-8')).hexdigest()
                    hash_yesterday = hashlib.sha256(content_yesterday.encode('utf-8')).hexdigest()
                    
                    is_changed = hash_yesterday != hash_today
                    is_first_run = not html_yesterday_raw

                    if is_first_run or is_changed:
                        if is_first_run:
                            print(f"  -> First run for {platform} - {name}. Saving baseline.")
                            notifications.append(f"Local test - Baseline for {platform} {name} has been saved.")
                        else:
                            print(f"  -> CHANGE DETECTED for {platform} - {name}!")
                            notifications.append(f"Local test - Change detected on {platform} {name}: {url}")
                        
                        filename = f"{platform}_{name}_base.png" if is_first_run else f"{platform}_{name}_diff_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
                        filepath = os.path.join(platform_path, filename)
                        take_scrolling_screenshot(driver, filepath)

                        with open(html_file_path, 'w', encoding='utf-8') as f:
                            f.write(html_today_raw)
                        print(f"  -> HTML saved to: {html_file_path}")
                    else:
                        print(f"  -> No change detected.")

            except Exception as e:
                print(f"  -> Error checking {platform} - {name}: {e}")
                import traceback
                traceback.print_exc()

    if notifications:
        print("\n--- Change Notifications (Local Test) ---")
        full_message = "（ローカルテスト通知）\n" + "\n\n".join(notifications)
        print(full_message)
        # ローカル実行時は実際にSlackに送らないようにコメントアウト
        send_slack_notification(full_message)
    else:
        print("\nNo website changes to notify.")

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
    # for handler in all_handlers:
    #     handler_name = handler.__name__.split('.')[-1]
    #     print(f"--- Processing {handler_name} ---")
        
    #     try:
    #         screenshot_paths, scraped_data = handler.process_data_and_screenshot(driver, output_dir)

    #         if screenshot_paths:
    #             saved_files.extend(screenshot_paths)
    #             print(f"  -> Got {len(screenshot_paths)} screenshot(s) from {handler_name}.")
            
    #         if scraped_data:
    #             all_scraped_data.extend(scraped_data)
    #             print(f"  -> Got {len(scraped_data)} data rows from {handler_name}.")

    #     except Exception as e:
    #         # ハンドラ実行中に予期せぬエラーが起きた場合
    #         print(f"!!! An unexpected error occurred in {handler_name}: {e}. Skipping.")

    # # Google Drive/GCSへの接続情報を再利用するために先に定義
    # try:
    #     creds, project = google_auth_default(scopes=[
    #         'https://www.googleapis.com/auth/spreadsheets',
    #         'https://www.googleapis.com/auth/drive',
    #         'https://www.googleapis.com/auth/devstorage.read_write' # GCSのスコープを追加
    #     ])
    #     drive_service = build('drive', 'v3', credentials=creds)
    # except Exception as e:
    #     print(f"Failed to authenticate with Google services: {e}")
    #     driver.quit()
    #     return "Authentication failed.", 500

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