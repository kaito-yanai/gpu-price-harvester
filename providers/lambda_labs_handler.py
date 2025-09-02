import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By

PRICING_URL = "https://lambda.ai/service/gpu-cloud"

# --- Helper Functions (コメントアウトされていたものを活用・修正) ---

def parse_price_lambda(price_str):
    """ "$2.99 / GPU / hr" のような価格文字列をfloatに変換する """
    if not price_str or "contact sales" in price_str.lower():
        return None
    match = re.search(r"[\$€£]?\s*(\d+\.?\d*)", price_str.replace(',', ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def parse_gpu_instance_name(gpu_name_str):
    """ "On-demand 8x NVIDIA H100 SXM" のような文字列を解析する """
    gpu_name_str = gpu_name_str.strip()
    num_chips = 1
    base_gpu_model = gpu_name_str
    
    match_chips = re.match(r"(?:On-demand\s+|Reserved\s+)?(\d+)x\s*(.*)", gpu_name_str, re.IGNORECASE)
    if match_chips:
        num_chips = int(match_chips.group(1))
        base_gpu_model = match_chips.group(2).strip()
        
    return num_chips, base_gpu_model

def get_canonical_variant_and_base_chip_lambda(base_gpu_model_name):
    """ GPU名を大分類に整理する """
    text_to_search = base_gpu_model_name.lower()
    family = None

    if "h100" in text_to_search:
        family = "H100"
    elif "gh200" in text_to_search or "h200" in text_to_search:
        family = "H200"
    elif "l40s" in text_to_search:
        family = "L40S"
    elif "b200" in text_to_search: # Blackwell世代
        family = "B200"
    
    return family

def fetch_lambda_labs_data(soup):
    """ Lambda Labsの価格ページHTMLから情報を抽出し、整形するメインの処理 """
    all_data = []
    
    # ページは8x, 4x, 2x, 1xのタブで構成されている
    # 各タブのコンテンツ（テーブル）をすべて探し出す
    tab_panels = soup.find_all('div', class_='comp-tabbed-content__tab-panel')
    if not tab_panels:
        print("ERROR (Lambda Labs): Could not find tab panels for GPU configurations.")
        return []

    for panel in tab_panels:
        table = panel.find('table')
        if not table or not table.tbody:
            continue

        for row in table.tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 6:
                continue

            gpu_name_full_str = cells[0].get_text(strip=True)
            price_per_gpu_hr_str = cells[5].get_text(strip=True)

            price_per_gpu_hr = parse_price_lambda(price_per_gpu_hr_str)
            if price_per_gpu_hr is None:
                continue # "CONTACT SALES" や価格なしはスキップ

            num_chips, base_gpu_model = parse_gpu_instance_name(gpu_name_full_str)
            gpu_family = get_canonical_variant_and_base_chip_lambda(base_gpu_model)

            if not gpu_family:
                continue # 対象GPUでなければスキップ

            # インスタンス全体の時間単価を計算
            total_instance_price = num_chips * price_per_gpu_hr
            
            data_dict = {
                "Provider Name": "Lambda Labs",
                "GPU Variant Name": gpu_name_full_str,
                "Region": "US (TX, CA, UT)", # サイト情報から
                "GPU (H100 or H200 or L40S)": gpu_family,
                "Number of Chips": num_chips,
                "Total Price ($)": round(total_instance_price, 2)
            }
            all_data.append(data_dict)
            
    return all_data

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    """ Lambda Labsのページに一度アクセスし、スクリーンショットと価格データの両方を取得する """
    screenshot_filepaths = []
    scraped_data_list = []
    
    try:
        print(f"Navigating to: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5) 

        # 1. 8x, 4x, 2x, 1x のタブボタンをすべて見つける
        tab_buttons = driver.find_elements(By.CSS_SELECTOR, "button.comp-tabbed-content__tab-btn")
        print(f"Found {len(tab_buttons)} configuration tabs to screenshot.")

        # 2. 各タブボタンを順番にクリックしてスクリーンショットを撮影
        for button in tab_buttons:
            try:
                tab_name = button.text
                print(f"Processing tab: {tab_name}")
                
                # ボタンをクリックして表示を切り替え
                driver.execute_script("arguments[0].click();", button)
                # 表示が切り替わるのを少し待つ
                time.sleep(2)

                # フルページのスクリーンショットを撮影
                print(f"Taking full-page screenshot for {tab_name} tab...")
                driver.set_window_size(1920, 800)
                total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
                driver.set_window_size(1920, total_height)
                time.sleep(1)

                # タブ名を含めたユニークなファイル名を生成
                base_name = PRICING_URL.replace("https://", "").replace("www.", "").replace("/", "_")
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"{base_name}_{tab_name}_{timestamp}.png"
                filepath = f"{output_directory}/{filename}"
                
                driver.save_screenshot(filepath)
                print(f"Successfully saved screenshot to: {filepath}")
                
                # 成功したファイルパスをリストに追加
                screenshot_filepaths.append(filepath)

            except Exception as e_tab:
                print(f"Could not process tab '{button.text}'. Error: {e_tab}")

        # 価格テキストの取得（これは1回だけでOK。全タブのHTMLは最初から読み込まれているため）
        print("Scraping pricing data from the page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list = fetch_lambda_labs_data(soup)

        # 収集したファイルパスのリストと、価格データのリストを返す
        return screenshot_filepaths, scraped_data_list

    except Exception as e:
        print(f"An error occurred during Lambda Labs processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []