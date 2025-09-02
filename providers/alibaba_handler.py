import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

PRICING_URL = "https://www.alibabacloud.com/en/product/machine-learning/pricing?_p_lc=1"

def get_canonical_variant_and_base_chip_alibaba(billing_item):
    """
    Alibaba Cloudの請求項目名から、GPUの大分類を判別するヘルパー関数
    """
    item_lower = billing_item.lower()
    # 今後、H100などが追加された場合を想定して拡張可能な作りに
    if "v100" in item_lower:
        return "V100"
    if "t4" in item_lower:
        return "T4"
    if "p100" in item_lower:
        return "P100"
    if "m40" in item_lower:
        return "M40"
    # 対象外のGPUやCPUの場合はNoneを返す
    return None

def fetch_alibaba_data(soup):
    """
    Alibaba Cloudの価格ページHTMLから情報を抽出し、整形するメインの処理
    """
    all_data = []
    
    try:
        # 3つある価格表の中から「PAI DSW Billing Table」を探す
        dsw_header = soup.find('h4', string=re.compile("PAI  DSW Billing Table"))
        if not dsw_header:
            print("ERROR (Alibaba): Could not find 'PAI DSW Billing Table'.")
            return []

        # ヘッダーの次にあるテーブルを取得
        table = dsw_header.find_next_sibling('div', class_='table-item-row').find('table')
        if not table:
            print("ERROR (Alibaba): Could not find the table following the DSW header.")
            return []

        # テーブルの各行をループ処理
        for row in table.tbody.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) < 3:
                continue

            # 各セルから情報を抽出
            billing_item = cells[0].get_text(strip=True)
            price_text = cells[1].get_text(strip=True)
            region = cells[2].get_text(strip=True)

            # GPUの行のみを対象とする
            if "GPU" not in billing_item:
                continue

            # 大分類を判別
            gpu_type = get_canonical_variant_and_base_chip_alibaba(billing_item)
            if not gpu_type:
                continue # 対象GPUでなければスキップ

            # 価格を数値として抽出 (例: "US$4.5/GPU/Hour" -> 4.5)
            price_match = re.search(r'[\d\.]+', price_text)
            price = float(price_match.group(0)) if price_match else "N/A"

            # データをスプレッドシートの形式に合わせて辞書に格納
            data_dict = {
                "Provider Name": "Alibaba Cloud",
                "GPU Variant Name": billing_item, # Variation
                "Region": region,
                "GPU (H100 or H200 or L40S)": gpu_type, # GPU_Type
                "Number of Chips": 1, # Size (1xと仮定)
                "Total Price ($)": price # Price
                # その他の固定値や取得できない情報はmain.py側で補完
            }
            all_data.append(data_dict)

    except Exception as e:
        print(f"An error occurred during Alibaba data fetching: {e}")
        import traceback
        traceback.print_exc()
        
    return all_data

def create_timestamped_filename(url):
    url_without_query = url.split('?')[0]
    base_name = url_without_query.replace("https://", "").replace("http://", "").replace("www.", "")
    safe_base_name = re.sub(r'[\\/*:"<>|]', '_', base_name).replace('/', '_')
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{safe_base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
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

        print("Scraping pricing data from the same page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data_list = fetch_alibaba_data(soup)

        return [filepath] if filepath else [], scraped_data_list

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []