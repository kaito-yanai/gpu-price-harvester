import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://www.anyscale.com/pricing"

def get_canonical_variant_and_base_chip_anyscale(gpu_name):
    """
    AnyscaleのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    item_lower = gpu_name.lower()
    # H100, H200は現在リストにないが、将来の追加を想定
    if "h100" in item_lower:
        return "H100"
    if "h200" in item_lower:
        return "H200"
    if "l40s" in item_lower:
        return "L40S"
    if "t4" in item_lower:
        return "T4"
    if "l4" in item_lower:
        return "L4"
    if "a10g" in item_lower:
        return "A10G"
    if "v100" in item_lower:
        return "V100"
    if "a100" in item_lower:
        return "a100"
    return None # 対象外の場合はNoneを返す

def fetch_anyscale_data(soup):
    """
    Anyscaleの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 「Deploy in Anyscale’s Cloud」のセクションを特定
        anyscale_cloud_section = soup.find('section', id="deploy-in-anyscale’s-cloud")
        if not anyscale_cloud_section:
            print("ERROR (Anyscale): Could not find the 'Deploy in Anyscale’s Cloud' section.")
            return []

        # そのセクション内の価格テーブルを探す
        table = anyscale_cloud_section.find('table', class_="table-striped")
        if not table:
            print("ERROR (Anyscale): Could not find the pricing table within the section.")
            return []

        for row in table.tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            gpu_name = cells[0].get_text(strip=True)
            price_text = cells[1].get_text(strip=True)

            # GPUの大分類を判別し、対象外はスキップ
            gpu_type = get_canonical_variant_and_base_chip_anyscale(gpu_name)
            if not gpu_type:
                continue

            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"

            data_dict = {
                "Provider Name": "Anyscale",
                "GPU Variant Name": gpu_name,
                "Region": "N/A", # ページに記載がないためN/A
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": 1, # 1GPUあたりの価格なので1x
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Anyscale data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def take_screenshot(driver, output_directory):
    filepath = None
    scraped_data_list = []

    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        # ページが読み込まれるのを待つ
        time.sleep(3)

        # --- Anyscale特有の操作 ---
        try:
            print("Looking for the 'hr' button to click...")
            wait = WebDriverWait(driver, 10)
            
            # 「Deploy in Anyscale’s Cloud」セクション内にある「hr」ボタンを正確に特定する
            hr_button_xpath = "//section[@id='deploy-in-anyscale’s-cloud']//button[text()='hr']"
            hr_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, hr_button_xpath))
            )
            
            print("'hr' button found. Clicking it.")
            hr_button.click()
            time.sleep(2) # 価格が更新されるのを待つ
        except TimeoutException:
            print("Could not find the 'hr' button. It might be active by default or the page structure has changed.")
        
        # --- スクリーンショット撮影とデータ取得 ---
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
        
        scraped_data_list = fetch_anyscale_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []