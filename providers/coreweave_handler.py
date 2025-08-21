import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://www.coreweave.com/pricing"

def get_canonical_variant_and_base_chip_coreweave(gpu_name_on_page):
    """
    CoreWeaveのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text_to_search = str(gpu_name_on_page).lower()
    if "h100" in text_to_search:
        return "H100"
    if "h200" in text_to_search or "gh200" in text_to_search:
        return "H200"
    if "l40s" in text_to_search:
        return "L40S"
    if "b200" in text_to_search or "gb200" in text_to_search:
        return "B200"
    if "a100" in text_to_search:
        return "A100"
    return None

def fetch_coreweave_data(soup):
    """
    CoreWeaveの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # GPU製品が含まれる可能性のある行をすべて選択
        # HTMLの構造から、これらのクラスを持つ行がGPU製品に対応
        rows = soup.select('.table-row.w-dyn-item.gpu-pricing, .table-row.w-dyn-item.kubernetes-gpu-pricing, .table-row.w-dyn-item.gpu-pricing-and-kubernetes-gpu-pricing')
        
        print(f"Found {len(rows)} potential GPU rows.")

        for row in rows:
            # 各セルの情報を取得
            cells = row.find('div', class_='table-grid').find_all('div', class_='table-v2-cell', recursive=False)
            if len(cells) < 7:
                continue

            gpu_name = cells[0].get_text(strip=True)
            gpu_count_text = cells[1].get_text(strip=True)
            price_text = cells[6].get_text(strip=True)
            
            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_coreweave(gpu_name)
            if not gpu_type:
                continue # 対象GPUでなければスキップ

            # 価格を数値として抽出
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue # 価格がなければスキップ

            # GPU数を数値として抽出
            count_match = re.search(r'(\d+)', gpu_count_text)
            num_chips = int(count_match.group(1)) if count_match else 1
            
            data_dict = {
                "Provider Name": "CoreWeave",
                "GPU Variant Name": gpu_name,
                "Region": "US", # サイトから US Data Centers と判断
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during CoreWeave data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    CoreWeaveのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        
        # ページの主要な価格テーブルが表示されるまで待機
        try:
            print("Waiting for pricing table to load...")
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.table-v2.kubernetes-gpu-pricing")))
            print("Pricing table loaded.")
        except TimeoutException:
            print("Pricing table did not load within 10 seconds. Proceeding anyway.")

        # フルページのスクリーンショットを撮影
        print("Taking full-page screenshot...")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")

        # 価格テキストの取得
        print("Scraping pricing data from the same page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data_list = fetch_coreweave_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during CoreWeave processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []