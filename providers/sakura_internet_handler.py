# providers/sakura_internet_handler.py
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from currency_converter import CurrencyConverter

# --- URL定義 ---
# こちらのページからのみ価格を取得する
SAKURA_CLOUD_GPU_URL = "https://cloud.sakura.ad.jp/products/server/gpu/" 
# こちらのページは価格情報がないため、スクリーンショットのみ
SAKURA_KOUKARYOKU_URL = "https://www.sakura.ad.jp/koukaryoku-phy/"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "SAKURA internet"
STATIC_SERVICE_PROVIDED = "Cloud GPU Server"
STATIC_REGION_INFO = "Tokyo / Ishikari" # Based on general knowledge

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _fetch_cloud_gpu_data(soup):
    """
    さくらのクラウドGPUページの価格表からデータを抽出する
    """
    final_sheet_rows_unpivoted = []

    table = soup.find('table', class_='price-list_02')
    if not table:
        print("ERROR (SAKURA): Could not find the pricing table '.price-list_02'. HTML structure may have changed.")
        return []
    
    # 料金テーブルの各行を取得
    rows = table.tbody.find_all('tr')[1:] 
    if not rows:
        print("ERROR (SAKURA): Could not find pricing rows '.comparison-table__body__row'. HTML structure may have changed.")
        return []

    print(f"Found {len(rows)} SAKURA Cloud GPU offerings.")

    for row in rows:
        try:
            cells = row.find_all(['th', 'td'])
            if len(cells) < 4:
                continue

            # --- データの取得 ---
            display_name = cells[0].get_text(strip=True)
            hourly_price_text = cells[3].get_text(strip=True)

            # --- データの整形 ---
            base_chip_category = "N/A"
            if "H100" in display_name:
                base_chip_category = "H100"
            elif "V100" in display_name: # 参考情報としてV100も取得
                base_chip_category = "V100"
            else:
                continue # 監視対象外

            # このページではチップ数は常に1
            num_chips = 1
            gpu_variant_name = display_name

            hourly_price_match = re.search(r'([\d,]+)円', hourly_price_text)
            hourly_price = float(hourly_price_match.group(1).replace(',', '')) if hourly_price_match else 0
            
            base_info_for_row = {
                "Provider Name": STATIC_PROVIDER_NAME,
                "Currency": "JPY",
                "Service Provided": STATIC_SERVICE_PROVIDED,
                "Region": STATIC_REGION_INFO,
                "GPU ID": display_name,
                "GPU (H100 or H200 or L40S)": base_chip_category,
                "Display Name(GPU Type)": display_name,
                "GPU Variant Name": gpu_variant_name,
            }
            
            row_hourly_data = {
                **base_info_for_row,
                "Number of Chips": num_chips,
                "Period": "Per Hour",
                "Total Price ($)": hourly_price, # JPY
                "Effective Hourly Rate ($/hr)": hourly_price / num_chips # JPY
            }
            final_sheet_rows_unpivoted.append(row_hourly_data)

        except Exception as e:
            print(f"ERROR (SAKURA): Failed to process a row. DisplayName: {display_name}. Error: {e}")
            import traceback
            traceback.print_exc()
            
    return final_sheet_rows_unpivoted


def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    c = CurrencyConverter()

    # --- 1. さくらのクラウドGPU ---
    try:
        print(f"Navigating to SAKURA Cloud GPU: {SAKURA_CLOUD_GPU_URL}")
        driver.get(SAKURA_CLOUD_GPU_URL)
        time.sleep(5)

        print("Taking full-page screenshot of SAKURA Cloud GPU...")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(SAKURA_CLOUD_GPU_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping pricing data from SAKURA Cloud GPU page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        # データ取得関数を呼び出し
        scraped_data = _fetch_cloud_gpu_data(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)
        
    except Exception as e:
        print(f"An error occurred during SAKURA Cloud GPU processing: {e}")
        import traceback
        traceback.print_exc()

    # --- 2. さくらの高火力PHY（スクリーンショットのみ） ---
    try:
        print(f"Navigating to SAKURA Koukaryoku PHY: {SAKURA_KOUKARYOKU_URL}")
        driver.get(SAKURA_KOUKARYOKU_URL)
        time.sleep(5)
        
        print("Taking full-page screenshot of SAKURA Koukaryoku PHY...")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(SAKURA_KOUKARYOKU_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)
        
    except Exception as e:
        print(f"An error occurred during SAKURA Koukaryoku PHY processing: {e}")
        import traceback
        traceback.print_exc()

    # --- 3. 通貨変換処理 ---
    final_data_usd = []
    if scraped_data_list:
        print(f"Converting {len(scraped_data_list)} rows from JPY to USD...")
        for data in scraped_data_list:
            try:
                # 元の価格を取得
                original_price = data["Total Price ($)"]
                original_rate = data["Effective Hourly Rate ($/hr)"]
                
                # USDに変換
                usd_price = c.convert(original_price, 'JPY', 'USD')
                usd_rate = c.convert(original_rate, 'JPY', 'USD')
                
                # データをUSDの値で更新
                data["Total Price ($)"] = round(usd_price, 4)
                data["Effective Hourly Rate ($/hr)"] = round(usd_rate, 4)
                data["Currency"] = "USD"
                final_data_usd.append(data)
            except Exception as e:
                print(f"Currency conversion failed for row {data.get('GPU ID')}: {e}. Skipping row.")

    return saved_files, scraped_data_list