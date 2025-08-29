# providers/hyperstack_handler.py

import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.hyperstack.cloud/gpu-pricing"

def get_canonical_variant_and_base_chip_hyperstack(gpu_name_str):
    """
    HyperstackのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text = gpu_name_str.lower()
    if 'h200' in text:
        return "H200"
    if 'h100' in text:
        return "H100"
    if 'l40s' in text or 'l40' in text: # L40SとL40をL40Sとして分類
        return "L40S"
    # その他追跡対象
    if 'a100' in text:
        return "A100"
    if 'b200' in text or 'gb200' in text:
        return "B200"
    return None

def fetch_hyperstack_data(soup):
    """
    Hyperstackの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 価格情報が含まれる親コンテナを特定
        container = soup.find('div', id='cloud-pricing')
        if not container:
            print("ERROR (Hyperstack): Could not find the main pricing container (id='cloud-pricing').")
            return []

        # 「On-Demand GPU Pricing」のカードを探す
        on_demand_card = None
        all_cards = container.select('div.page-price_card')
        for card in all_cards:
            title_tag = card.select_one('h3')
            if title_tag and 'On-Demand GPU' in title_tag.get_text():
                on_demand_card = card
                break
        
        if not on_demand_card:
            print("ERROR (Hyperstack): Could not find the 'On-Demand GPU' pricing card.")
            return []

        # On-Demandカード内の各行をループ
        for row in on_demand_card.select('div.page-price_card_row_item'):
            cols = row.select('div[class*="_col"]')
            if len(cols) < 5:
                continue

            variation = cols[0].get_text(strip=True)
            price_text = cols[4].get_text(strip=True)

            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_hyperstack(variation)
            if not gpu_type:
                continue

            # 価格を数値として抽出
            price_match = re.search(r"(\d+\.?\d*)", price_text.replace('$', ''))
            price = float(price_match.group(1)) if price_match else "N/A"
            if price == "N/A":
                continue

            data_dict = {
                "Provider Name": "Hyperstack",
                "GPU Variant Name": variation,
                "Region": "Europe, North America", # サイトから判断
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": 1,
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Hyperstack data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Hyperstackのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5) 

        # フルページのスクリーンショットを撮影
        print("Taking full-page screenshot...")
        driver.set_window_size(1920, 800)
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
        
        scraped_data_list = fetch_hyperstack_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Hyperstack processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []