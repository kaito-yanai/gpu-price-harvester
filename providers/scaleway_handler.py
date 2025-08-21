import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from currency_converter import CurrencyConverter

# --- URL定義 ---
SCALEWAY_H100_URL = "https://www.scaleway.com/en/h100-pcie-try-it-now/"
SCALEWAY_L40S_URL = "https://www.scaleway.com/en/l40s-gpu-instance/"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Scaleway"
STATIC_SERVICE_PROVIDED = "Scaleway GPU Instances"
STATIC_REGION_INFO = "Paris (PAR2)" # HTMLから正確な情報を特定
STATIC_STORAGE_OPTION = "Local NVMe SSD / Block Storage"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '€2.73/hour' のような文字列から数値（2.73）を抽出する """
    if not price_str:
        return None
    # '€'や'/hour'などの不要な文字を削除
    price_str_cleaned = price_str.replace('€', '').replace('/hour', '').strip()
    match = re.search(r"(\d+\.?\d*)", price_str_cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _fetch_h100_data(soup):
    """ H100ページの価格表からデータを抽出する """
    final_sheet_rows_unpivoted = []
    
    # h2見出しを探し、その次にあるテーブルを取得
    section_heading = soup.find('h2', string=re.compile("Choose your instance's format"))
    if not section_heading:
        print("ERROR (Scaleway H100): Could not find pricing section header.")
        return []
    
    table = section_heading.find_next('div', {'class': 'Table_table__6cXug'})
    if not table:
        print("ERROR (Scaleway H100): Could not find pricing table.")
        return []

    rows = table.find('tbody').find_all('tr')
    print(f"Found {len(rows)} Scaleway H100 offerings.")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue

        instance_name = cols[0].get_text(strip=True)
        gpu_spec_str = cols[1].get_text(strip=True)
        price_str = cols[4].get_text(strip=True)
        
        # GPUタイプの判定
        gpu_variant_name = "N/A"
        base_chip_category = "H100" # このページはH100固定
        if "H100 PCIe" in gpu_spec_str:
            gpu_variant_name = "H100 PCIe"
        elif "H100 Tensor Core" in gpu_spec_str: # SXMを示唆
            gpu_variant_name = "H100 SXM"
        
        num_chips_match = re.search(r'(\d+)', gpu_spec_str)
        num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
        
        hourly_price = _parse_price(price_str)
        if hourly_price is None:
            continue

        base_info_for_row = {
            "Provider Name": STATIC_PROVIDER_NAME,
            "Currency": "EUR", # 通貨をEURと明記
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO,
            "GPU ID": instance_name,
            "GPU (H100 or H200 or L40S)": base_chip_category,
            "Memory (GB)": 80, # H100は80GB
            "Display Name(GPU Type)": instance_name,
            "GPU Variant Name": gpu_variant_name,
            "Storage Option": STATIC_STORAGE_OPTION,
            "Amount of Storage": "Up to 12.8TB Scratch Storage",
            "Network Performance (Gbps)": "Up to 20 Gbps",
        }

        row_hourly_data = {
            **base_info_for_row,
            "Number of Chips": num_chips,
            "Period": "Per Hour",
            # Total Price ($)列にユーロの値を格納
            "Total Price ($)": hourly_price,
            "Effective Hourly Rate ($/hr)": hourly_price / num_chips,
        }
        final_sheet_rows_unpivoted.append(row_hourly_data)
        
    return final_sheet_rows_unpivoted

def _fetch_l40s_data(soup):
    """ L40Sページの価格表からデータを抽出する """
    final_sheet_rows_unpivoted = []

    section_heading = soup.find('h2', string=re.compile("Scale your infrastructure effortlessly"))
    if not section_heading:
        print("ERROR (Scaleway L40S): Could not find pricing section header.")
        return []
        
    table = section_heading.find_next('div', {'class': 'Table_table__6cXug'})
    if not table:
        print("ERROR (Scaleway L40S): Could not find pricing table.")
        return []

    rows = table.find('tbody').find_all('tr')
    print(f"Found {len(rows)} Scaleway L40S offerings.")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue

        instance_name = cols[0].get_text(strip=True)
        gpu_spec_str = cols[1].get_text(strip=True)
        price_str = cols[4].get_text(strip=True)

        base_chip_category = "L40S"
        gpu_variant_name = "L40S"
        
        num_chips_match = re.search(r'(\d+)', gpu_spec_str)
        num_chips = int(num_chips_match.group(1)) if num_chips_match else 1
        
        hourly_price = _parse_price(price_str)
        if hourly_price is None:
            continue
            
        base_info_for_row = {
            "Provider Name": STATIC_PROVIDER_NAME,
            "Currency": "EUR", # 通貨をEURと明記
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": STATIC_REGION_INFO,
            "GPU ID": instance_name,
            "GPU (H100 or H200 or L40S)": base_chip_category,
            "Memory (GB)": 48, # L40Sは48GB
            "Display Name(GPU Type)": instance_name,
            "GPU Variant Name": gpu_variant_name,
            "Storage Option": STATIC_STORAGE_OPTION,
            "Amount of Storage": "1.6TB Scratch Storage",
            "Network Performance (Gbps)": "2.5 Gbps",
        }

        row_hourly_data = {
            **base_info_for_row,
            "Number of Chips": num_chips,
            "Period": "Per Hour",
            # Total Price ($)列にユーロの値を格納
            "Total Price ($)": hourly_price,
            "Effective Hourly Rate ($/hr)": hourly_price / num_chips,
        }
        final_sheet_rows_unpivoted.append(row_hourly_data)
        
    return final_sheet_rows_unpivoted

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    c = CurrencyConverter()

    # --- 1. H100 ページの処理 ---
    try:
        print(f"Navigating to Scaleway H100: {SCALEWAY_H100_URL}")
        driver.get(SCALEWAY_H100_URL)
        time.sleep(5)

        print("Taking full-page screenshot of Scaleway H100...")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(SCALEWAY_H100_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved H100 screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping pricing data from H100 page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _fetch_h100_data(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Scaleway H100 processing: {e}")
        import traceback
        traceback.print_exc()

    # --- 2. L40S ページの処理 ---
    try:
        print(f"Navigating to Scaleway L40S: {SCALEWAY_L40S_URL}")
        driver.get(SCALEWAY_L40S_URL)
        time.sleep(5)

        print("Taking full-page screenshot of Scaleway L40S...")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(SCALEWAY_L40S_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved L40S screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping pricing data from L40S page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _fetch_l40s_data(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Scaleway L40S processing: {e}")
        import traceback
        traceback.print_exc()

    # --- 3. 通貨変換処理 ---
    final_data_usd = []
    if scraped_data_list:
        print(f"Converting {len(scraped_data_list)} rows from EUR to USD...")
        for data in scraped_data_list:
            try:
                # 元の価格を取得
                original_price = data["Total Price ($)"]
                original_rate = data["Effective Hourly Rate ($/hr)"]
                
                # USDに変換
                usd_price = c.convert(original_price, 'EUR', 'USD')
                usd_rate = c.convert(original_rate, 'EUR', 'USD')

                # データをUSDの値で更新
                data["Total Price ($)"] = round(usd_price, 4)
                data["Effective Hourly Rate ($/hr)"] = round(usd_rate, 4)
                data["Currency"] = "USD"
                final_data_usd.append(data)
            except Exception as e:
                print(f"Currency conversion failed for row {data.get('GPU ID')}: {e}. Skipping row.")

    return saved_files, scraped_data_list