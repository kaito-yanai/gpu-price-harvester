import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://www.cudocompute.com/pricing"

def get_canonical_variant_and_base_chip_cudo(gpu_name):
    """
    Cudo ComputeのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name.lower()
    if "h100" in name_lower:
        return "H100"
    if "h200" in name_lower:
        return "H200"
    if "l40s" in name_lower:
        return "L40S"
    # B200やGB200も将来のために追加
    if "b200" in name_lower or "gb200" in name_lower:
        return "B200"
    # その他追跡したいGPU
    if "a100" in name_lower:
        return "A100"
        
    return None # 対象外の場合はNoneを返す

def fetch_cudocompute_data(soup):
    """
    Cudo Computeの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        table = soup.find('table')
        if not table:
            print("ERROR (Cudo Compute): Could not find the pricing table.")
            return []

        for row in table.tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2: # 少なくともGPU名と価格のセルが必要
                continue
            
            # GPU名 (Variation)
            gpu_name_tag = cells[0].select_one('span.font-medium')
            variation = gpu_name_tag.get_text(strip=True) if gpu_name_tag else "N/A"

            # GPUの大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_cudo(variation)
            if not gpu_type:
                continue # 対象GPUでなければスキップ

            # On-demand価格
            price_tag = cells[1].select_one('span.font-bold span span')
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            
            # "Pricing on request" のような価格が設定されていない行はスキップ
            if not price_text or not price_text.startswith('$'):
                continue

            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"

            data_dict = {
                "Provider Name": "Cudo Compute",
                "GPU Variant Name": variation,
                "Region": "Global", # ページに個別記載がないため
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": 1, # 1GPUあたりの価格
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Cudo Compute data fetching: {e}")
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
        try:
            print("Looking for the cookie consent pop-up...")
            # 最大10秒間、指定したボタンがクリック可能になるまで待機する
            wait = WebDriverWait(driver, 10)
            
            # XPathを使って「'Decline optional cookies'というテキストを含むbutton要素」を探す
            decline_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Decline optional cookies')]"))
            )
            
            print("Found the 'Decline' button. Clicking it...")
            decline_button.click()
            
            # ポップアップが消えるのを少し待つ
            time.sleep(2)
            print("Cookie pop-up dismissed.")
            
        except Exception as e:
            # ポップアップが見つからない場合でも処理を続行
            print(f"Cookie pop-up not found or could not be clicked. Proceeding anyway. Error: {e}")

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
        
        scraped_data_list = fetch_cudocompute_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []