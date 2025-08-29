import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://modal.com/pricing"

def get_canonical_variant_and_base_chip_modal(gpu_name_str):
    """
    ModalのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    name_lower = gpu_name_str.lower()
    if "h100" in name_lower:
        return "H100"
    if "h200" in name_lower:
        return "H200"
    if "b200" in name_lower or "gb200" in name_lower:
        return "B200"
    if "l40s" in name_lower:
        return "L40S"
    if "a100" in name_lower:
        return "A100"
    return None

def fetch_modal_data(soup):
    """
    Modalの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # 「GPU Tasks」という見出しを探す
        gpu_header = soup.find('p', string=re.compile("GPU Tasks"))
        if not gpu_header:
            print("ERROR (Modal): Could not find the 'GPU Tasks' section.")
            return []

        # GPU価格リストのコンテナ（見出しの次のdiv）を取得
        gpu_list_container = gpu_header.find_next_sibling('div')
        if not gpu_list_container:
            print("ERROR (Modal): Could not find the container for the GPU list.")
            return []

        # 各GPUの行をループ
        for item in gpu_list_container.find_all('div', class_='line-item'):
            gpu_name_tag = item.find('p', class_='text-light-green/60')
            price_tag = item.find('p', class_='price')

            if not gpu_name_tag or not price_tag:
                continue

            variation = gpu_name_tag.get_text(strip=True)
            price_text = price_tag.get_text(strip=True)

            gpu_type = get_canonical_variant_and_base_chip_modal(variation)
            if not gpu_type:
                continue

            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"
            if price == "N/A":
                continue
            
            # チップ数を名前から抽出 (例: "2x ...")
            size_match = re.match(r'(\d+)x', variation, re.IGNORECASE)
            num_chips = int(size_match.group(1)) if size_match else 1

            data_dict = {
                "Provider Name": "Modal",
                "GPU Variant Name": variation,
                "Region": "Global", # ページに個別記載がないため
                "GPU (H100 or H200 or L40S)": gpu_type,
                "Number of Chips": num_chips,
                "Total Price ($)": price
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Modal data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    Modalのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(3)

        # --- Modal特有の操作 ---
        try:
            print("Looking for the 'Per hour' button to click...")
            wait = WebDriverWait(driver, 10)
            
            # "Per hour" というテキストを持つdiv要素を探してクリック
            hour_button_container_xpath = "//button[contains(., 'Per hour') and contains(., 'Per second')]"
            
            # ページに複数のボタンがある可能性を考慮し、「Compute costs」の見出しの下にあるボタンに限定する
            button_xpath = "//h3[text()='Compute costs']/following-sibling::div//button"

            hour_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            
            print("'Per hour' button found. Clicking it.")
            hour_button.click()
            time.sleep(2) # 価格が更新されるのを待つ
        except TimeoutException:
            print("Could not find the 'Per hour' button. It might be active by default or the page structure has changed.")
            
        # --- スクリーンショット撮影とデータ取得 ---
        print("Taking full-page screenshot...")
        driver.set_window_size(1920, 800)
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
        
        scraped_data_list = fetch_modal_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during Modal processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []