import time
from datetime import datetime
from bs4 import BeautifulSoup
import re

PRICING_URL = "https://www.civo.com/pricing"

def get_canonical_variant_and_base_chip_civo(section_title, row_title):
    """
    CivoのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    # 両方のテキストを結合して小文字にし、判断材料とする
    text_to_search = (section_title + " " + row_title).lower()
    
    if "h100" in text_to_search:
        return "H100"
    if "h200" in text_to_search:
        return "H200"
    if "l40s" in text_to_search:
        return "L40S"
    if "a100" in text_to_search:
        return "A100"
    if "b200" in text_to_search: # 将来のBlackwell B200用
        return "B200"
        
    return None # 対象外の場合はNoneを返す

def fetch_civo_data(soup):
    """
    Civoの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 「NVIDIA GPUs」のセクション全体を特定
        gpu_section = soup.find('section', id='nvidia-gpus')
        if not gpu_section:
            print("ERROR (Civo): Could not find the 'NVIDIA GPUs' section (id='nvidia-gpus').")
            return []

        # セクション内の個別のGPU価格表（L40S, A100など）をすべて見つける
        pricing_tables = gpu_section.find_all('div', id=re.compile("^nvidia-"))
        
        for table_div in pricing_tables:
            # テーブルの見出しからGPUの種類を取得 (例: "NVIDIA L40S 48GB GPU pricing")
            header_tag = table_div.find('h4')
            section_title = header_tag.get_text(strip=True) if header_tag else ""

            table = table_div.find('table')
            if not table:
                continue

            for row in table.tbody.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < 6: # On-demandとCommitmentの列があるか確認
                    continue
                
                # 'Size'のセルから情報を抽出
                size_cell = cells[0]
                variation = size_cell.get_text(separator=' ', strip=True) # Variation
                
                # GPUの大分類を判別
                gpu_type = get_canonical_variant_and_base_chip_civo(section_title, variation)
                if not gpu_type:
                    continue # 対象のGPUでなければスキップ

                # チップ数を抽出 (例: "8 x NVIDIA..." -> 8)
                size_match = re.search(r'(\d+)\s*x', variation)
                num_chips = int(size_match.group(1)) if size_match else 1 # Size

                # On-demand価格のセルを特定
                on_demand_cell = cells[5]
                hourly_price_div = on_demand_cell.find('div', {'data-option': 'hourly'})
                price_text = hourly_price_div.get_text(strip=True) if hourly_price_div else "N/A"
                
                price_match = re.search(r'[\d\.]+', price_text)
                price = float(price_match.group(0)) if price_match else "N/A"

                data_dict = {
                    "Provider Name": "Civo",
                    "GPU Variant Name": variation,
                    "Region": "US/EU",
                    "GPU (H100 or H200 or L40S)": gpu_type,
                    "Number of Chips": num_chips,
                    "Total Price ($)": price
                }
                all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Civo data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    filepath = None
    scraped_data_list = []

    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5) # ページ読み込み待機

        # フルページのスクリーンショットを撮影
        print("Taking full-page screenshot...")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")

        print("Scraping pricing data from the same page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data_list = fetch_civo_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []