# providers/vast_ai_handler.py

import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://console.vast.ai/create/"

def get_canonical_variant_and_base_chip_vast(gpu_model_from_page):
    """
    Vast.aiのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text_to_search = str(gpu_model_from_page).lower().strip()
    if "h100" in text_to_search:
        return "H100"
    if "h200" in text_to_search or "gh200" in text_to_search:
        return "H200"
    if "l40s" in text_to_search:
        return "L40S"
    return None

def fetch_vast_ai_data(soup):
    """
    Vast.aiの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    
    # 価格情報が記載された行をすべて見つける
    instance_rows = soup.select('div.machine-row')
    
    for row in instance_rows:
        try:
            # GPU名を特徴的なスタイルから特定
            gpu_name_tag = row.find(style=re.compile("font-size: 24px"))
            if not gpu_name_tag:
                continue
            
            variation = gpu_name_tag.get_text(strip=True)
            gpu_type = get_canonical_variant_and_base_chip_vast(variation)
            if not gpu_type:
                continue

            # 価格を取得
            price_tag = row.select_one('div.button-hover div.MuiBox-root')
            if not price_tag:
                continue
            
            price_text = price_tag.get_text(strip=True)
            price_match = re.search(r'[\$]?(\d+\.\d+)', price_text)
            price = float(price_match.group(1)) if price_match else "N/A"
            if price == "N/A":
                continue

            # チップ数を名前から抽出
            num_chips_match = re.match(r'^(\d+)x', variation)
            num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
            
            # リージョンを取得
            location_tag = row.find(style=re.compile("font-size: 11px"))
            region = location_tag.get_text(strip=True) if location_tag else "N/A"

            data_dict = {
                "Provider Name": "Vast.ai",
                "GPU Variant Name": variation,
                "Region": region,
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price
            }
            all_data.append(data_dict)
        except Exception:
            # 個別の行でエラーが発生しても処理を続ける
            continue
            
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Vast.aiのページで「Show More」を繰り返しクリックし、スクリーンショットと価格データを取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(10) # このページは初期読み込みに時間がかかるため長めに待つ

        # --- "Show More" ボタンを繰り返しクリック ---
        max_clicks = 1 # 無限ループを防ぐための最大クリック回数
        for i in range(max_clicks):
            try:
                print(f"Looking for 'Show More' button (Attempt {i+1}/{max_clicks})...")
                wait = WebDriverWait(driver, 5) # 5秒待ってボタンを探す
                show_more_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[text()='Show More']"))
                )
                # JavaScriptでクリックする方が確実
                driver.execute_script("arguments[0].click();", show_more_button)
                print("Clicked 'Show More'. Waiting for content to load...")
                time.sleep(3) # 新しいコンテンツが読み込まれるのを待つ
            except TimeoutException:
                print("'Show More' button not found. Assuming all content is loaded.")
                break # ボタンが見つからなければループを抜ける
        
        # --- スクリーンショット撮影とデータ取得 ---
        print("Taking full-page screenshot of all loaded content...")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")

        print("Scraping pricing data from the fully loaded page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data_list = fetch_vast_ai_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Vast.ai processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []