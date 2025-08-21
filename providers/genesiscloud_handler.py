import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.genesiscloud.com/pricing"

def get_canonical_variant_and_base_chip_genesis(gpu_name_on_page):
    """
    Genesis CloudのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text_to_search = str(gpu_name_on_page).lower()
    if "h100" in text_to_search:
        return "H100"
    if "h200" in text_to_search:
        return "H200"
    if "b200" in text_to_search or "gb200" in text_to_search:
        return "B200"
    if "l40s" in text_to_search:
        return "L40S"
    return None

def fetch_genesiscloud_data(soup):
    """
    Genesis Cloudの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # GPUの価格情報が含まれるカードをすべて見つける
        pricing_items = soup.find_all('div', class_='pricing-two-price-item')
        
        for item in pricing_items:
            title_tag = item.find('div', class_='pricing-two-price-title')
            variation = title_tag.get_text(strip=True) if title_tag else ""

            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_genesis(variation)
            if not gpu_type:
                continue # 対象GPUでなければスキップ

            # 価格情報を取得
            price_tag = item.find('div', class_='pricing-two-price-text')
            price_text = price_tag.get_text(strip=True) if price_tag else ""

            # RFQ (Request for Quote) や価格がないものはスキップ
            if "rfq" in price_text.lower() or '$' not in price_text:
                print(f"Skipping '{variation}' as price is RFQ or not available.")
                continue

            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue

            # 詳細説明からリージョンとチップ数を抽出
            description_tag = item.find('p', class_='pricing-two-price-content')
            description_text = description_tag.get_text(separator='\n', strip=True) if description_tag else ""
            
            # リージョンを抽出
            region_match = re.search(r"Data center locations?:\s*([^\n\r<]+)", description_text, re.IGNORECASE)
            region = region_match.group(1).strip() if region_match else "N/A"

            # チップ数を抽出 (例: "8x NVIDIA H100")
            size_match = re.search(r"(\d+)x\s+NVIDIA", description_text, re.IGNORECASE)
            num_chips = int(size_match.group(1)) if size_match else 1
            
            data_dict = {
                "Provider Name": "Genesis Cloud",
                "GPU Variant Name": variation,
                "Region": region,
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price # サイトの表記が per GPU per hour のためそのまま使用
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Genesis Cloud data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Genesis Cloudのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
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
        
        scraped_data_list = fetch_genesiscloud_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Genesis Cloud processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []