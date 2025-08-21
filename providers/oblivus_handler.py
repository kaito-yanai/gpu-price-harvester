import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://oblivus.com/pricing/"

def get_canonical_variant_and_base_chip_oblivus(gpu_name_str):
    """
    OblivusのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name_str.lower()
    if "h200" in name_lower:
        return "H200"
    if "h100" in name_lower:
        return "H100"
    if "l40s" in name_lower or "l40" in name_lower:
        return "L40S"
    if "a100" in name_lower:
        return "A100"
    return None

def fetch_oblivus_data(soup):
    """
    Oblivusの価格ページHTMLから、表示されているサマリーカードの情報のみを抽出する
    """
    all_data = []
    try:
        # GPUの価格情報が記載されているサマリーカードをすべて見つける
        pricing_cards = soup.find_all('div', class_='card-info-pricing')
        
        for card in pricing_cards:
            gpu_name_tag = card.find('h5', class_='card-title-pricing')
            price_button = card.find(['button', 'a'], class_='card-btn-pricing-2')

            if not gpu_name_tag or not price_button:
                continue

            variation = gpu_name_tag.get_text(strip=True)
            gpu_type = get_canonical_variant_and_base_chip_oblivus(variation)
            if not gpu_type:
                continue

            price_text = price_button.get_text(strip=True)
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue

            data_dict = {
                "Provider Name": "Oblivus",
                "GPU Variant Name": variation,
                "Region": "North America", # サイト情報から判断
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": 1, # 表示されている1GPUあたりの価格
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Oblivus data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Oblivusのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
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
        
        scraped_data_list = fetch_oblivus_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Oblivus processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []