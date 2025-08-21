import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from currency_converter import CurrencyConverter

# --- URL定義 ---
SEEWEB_CLOUD_GPU_URL = "https://www.seeweb.it/en/products/cloud-server-gpu"
SEEWEB_SERVERLESS_GPU_URL = "https://www.seeweb.it/en/products/serverless-gpu"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Seeweb"
STATIC_SERVICE_PROVIDED = "Seeweb Cloud GPU"
STATIC_REGION_INFO = "Europe (Italy, Switzerland)"
STATIC_STORAGE_OPTION = "Local NVMe SSD"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '1.60' や '1.52 €/hr' のような文字列から数値を抽出 """
    if not price_str: return None
    match = re.search(r"(\d+\.?\d*)", price_str.replace(',', '.'))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _get_gpu_info(gpu_name_on_card):
    """ カードのGPU名から情報を分類 """
    text = gpu_name_on_card.lower()
    if "h200" in text: return "H200", "H200 SXM", 141
    if "h100" in text: return "H100", "H100 SXM", 80
    if "l40s" in text: return "L40S", "L40S PCIe", 48
    return None, None, 0

def _parse_seeweb_page(soup, page_identifier):
    """ Seewebの価格ページを解析する共通関数 """
    final_sheet_rows_unpivoted = []
    
    product_cards = soup.select('div.cont-table.config div.cardType')
    if not product_cards:
        print(f"ERROR (Seeweb {page_identifier}): Could not find product cards.")
        return []

    print(f"Found {len(product_cards)} product cards on Seeweb {page_identifier} page.")

    for card in product_cards:
        gpu_name_tag = card.select_one('.card-header .cardname')
        if not gpu_name_tag: continue
        
        gpu_name = gpu_name_tag.get_text(strip=True)
        base_chip_category, gpu_variant_name, vram = _get_gpu_info(gpu_name)

        if not base_chip_category:
            continue # 監視対象外のGPUはスキップ

        # --- 価格情報の抽出 ---
        on_demand_price_tag = card.select_one('p.hourly span')
        per_gpu_hourly_price = _parse_price(on_demand_price_tag.get_text(strip=True)) if on_demand_price_tag else None
        
        # コミットメント割引（Cloud Server GPUページのみ存在）
        commit_prices = {}
        price_3m_tag = card.select_one('p.hourly_3mnths span')
        if price_3m_tag: commit_prices['3m'] = _parse_price(price_3m_tag.get_text(strip=True))
        
        price_6m_tag = card.select_one('p.hourly_6mnths span')
        if price_6m_tag: commit_prices['6m'] = _parse_price(price_6m_tag.get_text(strip=True))
        
        price_12m_tag = card.select_one('p.hourly_12mnths span')
        if price_12m_tag: commit_prices['12m'] = _parse_price(price_12m_tag.get_text(strip=True))

        if per_gpu_hourly_price is None:
            continue # 価格がなければスキップ

        # --- スペック情報の抽出 ---
        cpu_cores = card.select_one('span.cpuCore').get_text(strip=True) if card.select_one('span.cpuCore') else "N/A"
        ram_gb = card.select_one('span.ram').get_text(strip=True) if card.select_one('span.ram') else "N/A"
        disk_space_tag = card.select_one('span.disk')
        disk_space = disk_space_tag.get_text(strip=True) if disk_space_tag else "N/A"

        # --- GPU数（チップ数）の選択肢を抽出 ---
        chip_count_options = card.select('select.gpu-params option, select.serverless-gpu-params option')
        chip_counts = [int(opt['value']) for opt in chip_count_options if opt.get('value') and opt['value'].isdigit()]
        if not chip_counts:
            chip_counts = [1] # ドロップダウンがなければ1とする

        # --- チップ数ごとにデータ行を生成 ---
        for num_chips in chip_counts:
            total_hourly_price = per_gpu_hourly_price * num_chips
            
            base_info_for_row = {
                "Provider Name": STATIC_PROVIDER_NAME,
                "Currency": "EUR", # この時点ではEUR
                "Service Provided": f"{STATIC_SERVICE_PROVIDED} ({page_identifier})",
                "Region": STATIC_REGION_INFO,
                "GPU ID": f"seeweb_{page_identifier.lower()}_{num_chips}x_{gpu_variant_name.replace(' ','_')}",
                "GPU (H100 or H200 or L40S)": base_chip_category,
                "Memory (GB)": vram,
                "Display Name(GPU Type)": f"{num_chips}x {gpu_variant_name} ({cpu_cores} vCPU, {ram_gb}GB RAM)",
                "GPU Variant Name": gpu_variant_name,
                "Storage Option": STATIC_STORAGE_OPTION,
                "Amount of Storage": disk_space,
                "Network Performance (Gbps)": "10 Gbps",
                "Commitment Discount - 3 Month Price ($/hr per GPU)": commit_prices.get('3m'),
                "Commitment Discount - 6 Month Price ($/hr per GPU)": commit_prices.get('6m'),
                "Commitment Discount - 12 Month Price ($/hr per GPU)": commit_prices.get('12m'),
                "Number of Chips": num_chips,
                "Period": "Per Hour",
                "Total Price ($)": total_hourly_price, # インスタンス全体のEUR価格
                "Effective Hourly Rate ($/hr)": per_gpu_hourly_price, # GPU単価のEUR価格
            }
            final_sheet_rows_unpivoted.append(base_info_for_row)
            
    return final_sheet_rows_unpivoted

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list_eur = []
    c = CurrencyConverter()

    # --- 1. Cloud Server GPU ページの処理 ---
    try:
        print(f"Navigating to Seeweb Cloud Server GPU: {SEEWEB_CLOUD_GPU_URL}")
        driver.get(SEEWEB_CLOUD_GPU_URL)
        time.sleep(5)

        filename = create_timestamped_filename(SEEWEB_CLOUD_GPU_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping pricing data from Cloud Server GPU page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _parse_seeweb_page(soup, "CloudServerGPU")
        if scraped_data:
            scraped_data_list_eur.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Seeweb Cloud Server GPU processing: {e}")

    # --- 2. Serverless GPU ページの処理 ---
    try:
        print(f"Navigating to Seeweb Serverless GPU: {SEEWEB_SERVERLESS_GPU_URL}")
        driver.get(SEEWEB_SERVERLESS_GPU_URL)
        time.sleep(5)

        filename = create_timestamped_filename(SEEWEB_SERVERLESS_GPU_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping pricing data from Serverless GPU page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _parse_seeweb_page(soup, "ServerlessGPU")
        if scraped_data:
            scraped_data_list_eur.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Seeweb Serverless GPU processing: {e}")

    # --- 3. 通貨変換処理 (EUR -> USD) ---
    final_data_usd = []
    if scraped_data_list_eur:
        print(f"Converting {len(scraped_data_list_eur)} rows from EUR to USD...")
        for data in scraped_data_list_eur:
            try:
                # 価格に関連するすべてのキーをリストアップ
                price_keys = [
                    "Total Price ($)", "Effective Hourly Rate ($/hr)",
                    "Commitment Discount - 3 Month Price ($/hr per GPU)",
                    "Commitment Discount - 6 Month Price ($/hr per GPU)",
                    "Commitment Discount - 12 Month Price ($/hr per GPU)"
                ]
                for key in price_keys:
                    original_price = data.get(key)
                    if isinstance(original_price, (int, float)):
                        usd_price = c.convert(original_price, 'EUR', 'USD')
                        data[key] = round(usd_price, 4)
                
                data["Currency"] = "USD"
                final_data_usd.append(data)
            except Exception as e:
                print(f"Currency conversion failed for row {data.get('GPU ID')}: {e}. Skipping row.")
    
    return saved_files, final_data_usd