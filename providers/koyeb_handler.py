# providers/koyeb_handler.py

import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.koyeb.com/pricing"

def get_canonical_variant_and_base_chip_koyeb(gpu_name_str):
    """
    KoyebのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text_to_search = str(gpu_name_str).lower()
    family = None

    if "h100" in text_to_search:
        family = "H100"
    elif "l40s" in text_to_search:
        family = "L40S"
    elif "h200" in text_to_search: # 将来の追加を想定
        family = "H200"
    elif "a100" in text_to_search:
        family = "A100"
        
    return family

def fetch_koyeb_data(soup):
    """
    Koyebの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 「Serverless Compute」セクションを特定
        compute_section = soup.find('section', id='compute')
        if not compute_section:
            print("ERROR (Koyeb): Could not find the 'Compute' section (id='compute').")
            return []

        # デスクトップ表示用の価格グリッド（5列構成）を探す
        desktop_grid = compute_section.find('div', class_=re.compile("hidden.*grid-cols-5"))
        if not desktop_grid:
            print("ERROR (Koyeb): Could not find the 5-column desktop pricing grid.")
            return []

        # グリッド内のセルをすべて取得
        cells = desktop_grid.find_all('div', recursive=False)
        
        # 最初の5つはヘッダーなので、6番目から5つずつ処理する
        for i in range(5, len(cells), 5):
            instance_div, vcpu_div, ram_div, disk_div, price_div = cells[i:i+5]
            
            instance_name_tag = instance_div.find('div', class_='row')
            variation = instance_name_tag.get_text(strip=True) if instance_name_tag else "N/A"

            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_koyeb(variation)
            if not gpu_type:
                continue # GPUでなければスキップ

            price_text = price_div.get_text(strip=True)
            price_match = re.search(r"(\d+\.?\d*)", price_text.replace('$', ''))
            price = float(price_match.group(1)) if price_match else "N/A"
            if price == "N/A":
                continue

            # チップ数を名前から抽出 (例: "2x H100" -> 2)
            size_match = re.match(r'(\d+)x', variation, re.IGNORECASE)
            num_chips = int(size_match.group(1)) if size_match else 1
            
            data_dict = {
                "Provider Name": "Koyeb",
                "GPU Variant Name": variation,
                "Region": "US, Europe, Asia", # サイトから判断
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price # 表に記載の価格はインスタンス全体の価格
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Koyeb data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Koyebのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5) 

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
        
        scraped_data_list = fetch_koyeb_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Koyeb processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []