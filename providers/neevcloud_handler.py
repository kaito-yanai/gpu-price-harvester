import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://www.neevcloud.com/pricing.php"

def get_canonical_variant_and_base_chip_neev(gpu_name_from_site):
    """
    NeevCloudのGPU名から、GPUの大分類を判別するヘルパー関数
    """
    text_to_search = gpu_name_from_site.lower().replace("nvidia", "").strip()
    family = None
    if "h200" in text_to_search:
        family = "H200"
    elif "h100" in text_to_search:
        family = "H100"
    elif "l40s" in text_to_search:
        family = "L40S"
        
    return family

def fetch_neevcloud_data(soup):
    """
    NeevCloudの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    try:
        # AI SuperCloudセクションを特定
        main_section = soup.find('section', id='gpu-cloud')
        if not main_section:
            print("ERROR (NeevCloud): Could not find the main pricing section (id='gpu-cloud').")
            return []

        # セクション内の各GPUの見出し (h6) を探す
        gpu_headers = main_section.find_all('h6', class_='pricing_table_gpu_name')
        
        for header in gpu_headers:
            variation = header.get_text(strip=True).replace("Price", "").replace("Pricing", "").strip()
            gpu_type = get_canonical_variant_and_base_chip_neev(variation)
            if not gpu_type:
                continue

            # 見出しの直後にある価格カードのコンテナを探す
            container = header.find_next_sibling('div', class_=re.compile(r'row\s+mb-5'))
            if not container:
                continue

            # 各価格カードをループ
            for card in container.find_all('section', class_='pricing_choose_box'):
                # HGX H100/H200のようなコミットメントベースの価格カード
                if "HGX" in variation:
                    # 割引前の価格（On-demand価格）を探す
                    price_tag = card.find('h6', class_='pricing_choose_box_price_cross')
                    # もし割引前価格がなければ、割引後を暫定価格とする
                    if not price_tag:
                         price_tag = card.find('h5', class_='pricing_choose_box_heading')
                # A40/A30/L4などの単体GPU価格カード
                else:
                    price_tag = card.find('h5', class_='pricing_choose_box_heading')
                
                if not price_tag:
                    continue

                price_text = price_tag.get_text(strip=True)
                price_match = re.search(r'[\d\.]+', price_text)
                price = float(price_match.group(0)) if price_match else "N/A"
                if price == "N/A":
                    continue
                
                # チップ数はHGXなら8、それ以外は1と仮定
                num_chips = 8 if "HGX" in variation else 1

                # インスタンス全体の価格を計算 (価格は per GPU 表記のため)
                total_instance_price = price * num_chips

                data_dict = {
                    "Provider Name": "NeevCloud",
                    "GPU Variant Name": variation,
                    "Region": "US, India", # サイト情報から
                    "GPU (H100 or H200 or L40S)": gpu_type,
                    "Number of Chips": num_chips,
                    "Total Price ($)": round(total_instance_price, 2)
                }
                all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during NeevCloud data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """
    NeevCloudのページに一度アクセスし、スクリーンショットと価格データの両方を取得する
    """
    filepath = None
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        
        # --- NeevCloud特有の操作 ---
        try:
            print("Looking for the initial pop-up to close...")
            wait = WebDriverWait(driver, 10)
            # ポップアップ内の閉じるボタンを特定
            close_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div#popup button.close-btn"))
            )
            print("Pop-up found. Clicking the close button.")
            close_button.click()
            time.sleep(2)
        except TimeoutException:
            print("Pop-up not found. Proceeding anyway.")
            
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
        
        scraped_data_list = fetch_neevcloud_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during NeevCloud processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []