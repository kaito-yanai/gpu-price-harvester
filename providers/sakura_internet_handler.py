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
    
    # 料金テーブルの各行を取得
    rows = soup.select("div.comparison-table__body__row")
    if not rows:
        print("ERROR (SAKURA): Could not find pricing rows '.comparison-table__body__row'. HTML structure may have changed.")
        return []

    print(f"Found {len(rows)} SAKURA Cloud GPU offerings.")

    for row in rows:
        try:
            # --- GPU名とスペックの取得 ---
            # プラン名は header セルにある
            plan_name_tag = row.select_one(".comparison-table__body__cell--header .inner > a")
            display_name = plan_name_tag.get_text(strip=True) if plan_name_tag else "N/A"
            
            # スペックは別のセルにある
            spec_tags = row.select(".comparison-table__body__cell:not(.comparison-table__body__cell--header) .inner")
            
            # 例: ['NVIDIA A100 80GB ×1', '8vCPU / 94GB', 'ローカルSSD 3.84TB', '935円', '561,000円']
            specs_text = [tag.get_text(strip=True) for tag in spec_tags]

            gpu_type_text = specs_text[0] if len(specs_text) > 0 else ""
            cpu_ram_text = specs_text[1] if len(specs_text) > 1 else ""
            storage_text = specs_text[2] if len(specs_text) > 2 else ""
            hourly_price_text = specs_text[3] if len(specs_text) > 3 else "0"

            # --- データの整形 ---
            gpu_variant_name = "N/A"
            base_chip_category = "N/A"
            if "A100" in gpu_type_text:
                base_chip_category = "A100" # H100, H200, L40Sではないが、参考として取得
                gpu_variant_name = "NVIDIA A100 80GB"
            elif "L4" in gpu_type_text:
                base_chip_category = "L4" # L40Sではないが、参考として取得
                gpu_variant_name = "NVIDIA L4 24GB"
            else:
                continue # 監視対象外のGPUはスキップ

            num_chips_match = re.search(r'×(\d+)', gpu_type_text)
            num_chips = int(num_chips_match.group(1)) if num_chips_match else 1

            hourly_price_match = re.search(r'([\d,]+)円', hourly_price_text)
            hourly_price = float(hourly_price_match.group(1).replace(',', '')) if hourly_price_match else 0
            
            base_info_for_row = {
                "Provider Name": STATIC_PROVIDER_NAME,
                "Currency": "JPY",
                "Service Provided": STATIC_SERVICE_PROVIDED,
                "Region": STATIC_REGION_INFO,
                "GPU ID": display_name,
                "GPU (H100 or H200 or L40S)": base_chip_category,
                "Memory (GB)": "N/A", # HTMLからはVRAMが直接取れないため
                "Display Name(GPU Type)": display_name,
                "GPU Variant Name": gpu_variant_name,
                "Storage Option": "Local SSD",
                "Amount of Storage": storage_text,
                "Network Performance (Gbps)": "N/A",
                "Commitment Discount - 1 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 3 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 6 Month Price ($/hr per GPU)": "N/A",
                "Commitment Discount - 12 Month Price ($/hr per GPU)": "N/A",
                "Notes / Features": f"vCPU/RAM: {cpu_ram_text}"
            }
            
            # --- 1チップあたりの時間貸し料金行を生成 ---
            # このページではすでにNチップ構成の価格が表示されている
            row_hourly_data = {
                **base_info_for_row,
                "Number of Chips": num_chips,
                "Period": "Per Hour",
                "Total Price ($)": hourly_price, # JPYであることに注意
                "Effective Hourly Rate ($/hr)": hourly_price / num_chips
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