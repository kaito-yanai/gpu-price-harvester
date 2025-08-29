import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.tencentcloud.com/jp/document/product/1111/47656"

STATIC_PROVIDER_NAME = "Tencent Cloud"
STATIC_SERVICE_PROVIDED = "TDMQ for CMQ"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '0.2857' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def _fetch_api_prices(soup):
    api_data = []
    
    # "API call price" のヘッダーを探し、その次にあるテーブルを取得
    header = soup.find('h3', id='api-call-price')
    if not header:
        print("ERROR (Tencent Cloud): Could not find the pricing section header.")
        return []

    table_container = header.find_next("div", class_="table-container")
    if not table_container:
        print("ERROR (Tencent Cloud): Could not find the div with class 'table-container'.")
        return []
        
    table = table_container.find("table")
    if not table:
        print("ERROR (Tencent Cloud): Could not find the pricing table.")
        return []

    rows = table.select("tbody tr")
    if len(rows) < 2:
        return []

    # 1行目がリージョンヘッダー、2行目が価格
    region_cells = rows[0].find_all("td")[1:] # 最初の「Region」セルはスキップ
    price_cells = rows[1].find_all("td")[1:]  # 最初の単位セルはスキップ

    for i in range(len(region_cells)):
        try:
            region_name = region_cells[i].get_text(strip=True).replace(', ', ' | ')
            price = _parse_price(price_cells[i].get_text(strip=True))

            if price is not None:
                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME,
                    "Service Provided": STATIC_SERVICE_PROVIDED,
                    "Currency": "USD",
                    "Region": region_name,
                    "API_TYPE": "API Call",
                    "Period": "Per 1M Calls", # 単位を明確にする
                    "Total Price ($)": price,
                })
        except IndexError:
            # リージョンと価格の数が合わない場合はスキップ
            continue

    return api_data


def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Tencent Cloud Pricing: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5)

        print("Taking full-page screenshot")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping data from the page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data = _fetch_api_prices(soup)
        
        # APIデータ用のデフォルト値を設定
        for item in scraped_data:
            item.setdefault("GPU (H100 or H200 or L40S)", "")
            item.setdefault("GPU Variant Name", "N/A")
            item.setdefault("Number of Chips", "N/A")
            item.setdefault("Effective Hourly Rate ($/hr)", "N/A")
        
        scraped_data_list.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Tencent Cloud processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list