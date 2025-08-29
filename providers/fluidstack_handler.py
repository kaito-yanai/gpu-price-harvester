import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.fluidstack.io/pricing"

def get_canonical_variant_and_base_chip_fluidstack(gpu_name):
    """
    FluidStackのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name.lower()
    if "h100" in name_lower:
        return "H100"
    if "h200" in name_lower:
        return "H200"
    if "l40s" in name_lower:
        return "L40S"
    # Blackwell世代も追加
    if "b200" in name_lower or "gb200" in name_lower:
        return "B200" # 大分類としてB200に統一
    if "a100" in name_lower:
        return "A100"
        
    return None # 対象外の場合はNoneを返す

def fetch_fluidstack_data(soup):
    """
    FluidStackの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 価格カードが含まれる親コンテナを探す
        container = soup.find('div', class_='framer-67kbit')
        if not container:
            print("ERROR (FluidStack): Could not find the main pricing container.")
            return []

        # 各価格カードをループ処理
        # HTMLの構造から、直接の子divが価格カードに対応
        for card in container.find_all('div', recursive=False):
            # GPU名 (h3タグ)
            gpu_name_tag = card.find('h3')
            variation = gpu_name_tag.get_text(strip=True) if gpu_name_tag else ""

            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_fluidstack(variation)
            if not gpu_type:
                continue # 対象GPUでなければスキップ

            # 価格情報 (pタグ)
            price_container = card.find('div', attrs={'data-framer-name': re.compile(r'^\$|/ H$|On Request')})
            price_tag = price_container.find('p') if price_container else None
            price_text = price_tag.get_text(strip=True) if price_tag else ""

            # "On Request" の場合はスキップ
            if "on request" in price_text.lower():
                print(f"Skipping '{variation}' as price is 'On Request'.")
                continue

            # 価格を数値として抽出
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue

            data_dict = {
                "Provider Name": "FluidStack",
                "GPU Variant Name": variation,
                "Region": "Global", # ページに個別記載がないため
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": 1, # 1GPUあたりの価格
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during FluidStack data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    FluidStackのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
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
        
        scraped_data_list = fetch_fluidstack_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during FluidStack processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []