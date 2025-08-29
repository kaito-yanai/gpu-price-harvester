import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.liquidweb.com/gpu-hosting/"

def get_canonical_variant_and_base_chip_liquidweb(gpu_name):
    """
    Liquid WebのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name.lower()
    if "h100" in name_lower:
        return "H100"
    if "l40s" in name_lower:
        return "L40S"
    # L4は対象外かもしれないが、念のため分類
    if "l4" in name_lower:
        return "L4"
    return None

def fetch_liquidweb_data(soup):
    """
    Liquid Webの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # L4, L40S, H100など、各価格カードは類似の構造を持つ
        pricing_cards = soup.find_all('div', class_='kt-row-column-wrap')
        if not pricing_cards:
            print("ERROR (Liquid Web): Could not find any pricing cards with class 'kt-row-layout-inner'.")
            return []

        for card in pricing_cards:
            # GPU名を取得
            gpu_name_tag = card.find(class_=re.compile(r"kt-adv-heading\w+"))
            if not gpu_name_tag or "GB" not in gpu_name_tag.get_text():
                 continue
            variation = gpu_name_tag.get_text(strip=True)

            gpu_type = get_canonical_variant_and_base_chip_liquidweb(variation)
            if not gpu_type:
                continue

            # 価格が含まれるdivを探す
            price_container = card.find(class_=re.compile("kb-section-sm-dir-horizontal"))
            if not price_container:
                continue

            # 割引前の価格(<s>タグ)を除外し、現在の価格のみを取得
            current_price_tag = None
            price_divs = price_container.find_all('div', class_=re.compile("kt-adv-heading339095_"))
            for div in price_divs:
                if not div.find('s'): # <s>タグを含まないdivが現在の価格
                    current_price_tag = div
                    break
            
            if not current_price_tag:
                continue
            
            price_text = current_price_tag.get_text(strip=True)
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue

            # チップ数を名前から抽出（例: "(x2) H100 NVL 94GB" -> 2）
            size_match = re.search(r"\(x(\d+)\)", variation, re.IGNORECASE)
            num_chips = int(size_match.group(1)) if size_match else 1
            
            data_dict = {
                "Provider Name": "Liquid Web",
                "GPU Variant Name": variation,
                "Region": "US/EU", # データセンター情報から
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Liquid Web data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Liquid Webのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
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
        
        scraped_data_list = fetch_liquidweb_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Liquid Web processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []