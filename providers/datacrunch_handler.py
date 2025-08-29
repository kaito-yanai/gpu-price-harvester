import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://datacrunch.io/products"

def get_canonical_variant_and_base_chip_datacrunch(gpu_name_str):
    """
    DataCrunchのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name_str.lower()
    if "b200" in name_lower:
        return "B200"
    if "h200" in name_lower:
        return "H200"
    if "h100" in name_lower:
        return "H100"
    if "l40s" in name_lower:
        return "L40S"
    if "a100" in name_lower:
        return "A100"
    return None

def fetch_datacrunch_data(soup, current_gpu_type):
    """
    DataCrunchの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        target_header_img = soup.find('img', alt=current_gpu_type)
        if not target_header_img:
            print(f"ERROR (DataCrunch): Could not find the header image for {current_gpu_type}.")
            return []
        
        slide_section = target_header_img.find_parent('div', attrs={'data-slide': ''})
        if not slide_section:
            print(f"ERROR (DataCrunch): Could not find the parent slide section for {current_gpu_type}.")
            return []
        
        table = slide_section.find('table')

        if not table or not table.tbody:
            print(f"ERROR (DataCrunch): Could not find the pricing table for {current_gpu_type}.")
            return []

        for row in table.tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 8: # セルの数が足りない行はスキップ
                continue

            # 最初のセルからGPU名とチップ数を取得
            variation_cell = cells[0]
            variation = variation_cell.get_text(strip=True)
            num_chips = int(variation.split('x')[0]) if 'x' in variation else 1

            # 価格セルから情報を取得
            price_text = cells[7].get_text(strip=True)
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue

            data_dict = {
                "Provider Name": "DataCrunch",
                "GPU Variant Name": variation,
                "Region": "US/EU", # サイト情報から
                "GPU (H100 or H200 or L40S)": current_gpu_type, # ボタンから取得した現在のGPUタイプ
                "Number of Chips": num_chips,
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during DataCrunch data fetching for {current_gpu_type}: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url, section_name):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{section_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    DataCrunchのページで各GPUボタンを順番にクリックし、スクリーンショットと価格データを取得する
    """
    all_screenshot_paths = []
    all_scraped_data = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5) 

        # B200, H200, H100, L40S, A100 のボタンをすべて見つける
        gpu_buttons = driver.find_elements(By.XPATH, "//ul[@data-groups]//a")
        
        # 取得対象とするGPUのリスト
        target_gpus = ["B200", "H200", "H100", "L40S"]

        for button in gpu_buttons:
            gpu_name = button.text.strip()
            if gpu_name not in target_gpus:
                continue # 対象外のGPUボタンはスキップ
            
            try:
                print(f"--- Processing {gpu_name} section ---")
                # ボタンをクリックしてテーブルを更新
                button.click()
                time.sleep(3) # テーブルが更新されるのを待つ

                # スクリーンショット撮影
                print(f"Taking screenshot for {gpu_name}...")
                driver.set_window_size(1920, 800)
                total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
                driver.set_window_size(1920, total_height)
                time.sleep(1)

                filename = create_timestamped_filename(PRICING_URL, gpu_name)
                filepath = f"{output_directory}/{filename}"
                driver.save_screenshot(filepath)
                print(f"Successfully saved screenshot to: {filepath}")
                all_screenshot_paths.append(filepath)

                # 価格データ取得
                print(f"Scraping data for {gpu_name}...")
                html_source = driver.page_source
                soup = BeautifulSoup(html_source, "html.parser")
                scraped_data = fetch_datacrunch_data(soup, gpu_name)
                all_scraped_data.extend(scraped_data)

            except Exception as e_button:
                print(f"Could not process section for '{gpu_name}'. Error: {e_button}")

        return all_screenshot_paths, all_scraped_data

    except Exception as e:
        print(f"An error occurred during DataCrunch processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []