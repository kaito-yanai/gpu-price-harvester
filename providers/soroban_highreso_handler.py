import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from currency_converter import CurrencyConverter

# --- URL定義 ---
PRICING_URL_AISPACON = "https://soroban.highreso.jp/aispacon"
PRICING_URL_COMPUTE = "https://soroban.highreso.jp/compute"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Highreso Soroban"
STATIC_SERVICE_PROVIDED = "Soroban GPU Cloud"
STATIC_REGION_INFO = "Japan"
HOURS_IN_MONTH = 730 # 月の時間数

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price_jp(price_str):
    """ '¥2,783,000' や '￥50' のような文字列から数値を抽出 """
    if not price_str or '-' in price_str: return None
    price_cleaned = re.sub(r'[¥￥,円]', '', price_str)
    match = re.search(r'(\d+\.?\d*)', price_cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _get_gpu_info(gpu_str):
    """ 'NVIDIA A100 80GBx8枚' のような文字列から情報を抽出 """
    text = gpu_str.lower()
    num_chips = 1
    match = re.search(r'x(\d+)', text)
    if match:
        num_chips = int(match.group(1))

    if "h200" in text: return "H200", "H200 SXM", 141, num_chips
    if "a100" in text:
        vram = 80 if "80gb" in text else 40
        return "H100", "H100 (A100)", vram, num_chips # A100をH100カテゴリとして集計
    if "l40s" in text: return "L40S", "L40S", 48, num_chips
    
    return None, None, 0, 0

def _parse_aispacon_page(soup):
    """ aispaconページのH200月額料金テーブルを解析 """
    data_rows = []
    
    # 「AIスパコンクラウドの料金プラン」テーブルを探す
    header = soup.find(lambda tag: tag.name in ['h2', 'h3'] and "aiスパコンクラウドの料金プラン" in tag.get_text(strip=True).lower())
    if not header:
        print("ERROR (Soroban AISPACON): Could not find pricing plan table header.")
        return []
    
    table = header.find_next('table')
    if not table:
        print("ERROR (Soroban AISPACON): Could not find pricing table.")
        return []

    specs = {}
    rows = table.find_all('tr')
    for row in rows:
        cols = row.find_all(['th', 'td'])
        if len(cols) >= 2:
            key = cols[0].get_text(strip=True)
            value = cols[1].get_text(strip=True)
            specs[key] = value

    monthly_price_jpy = _parse_price_jp(specs.get("月額費用（税込み）", ""))
    gpu_spec_str = specs.get("GPU／ノード", "")

    if monthly_price_jpy and "h200" in gpu_spec_str.lower():
        base_chip, gpu_variant, vram, num_chips = _get_gpu_info(gpu_spec_str)
        
        # 月額料金から実効時間料金を計算
        per_gpu_hourly_price = (monthly_price_jpy / num_chips) / HOURS_IN_MONTH
        total_hourly_price = monthly_price_jpy / HOURS_IN_MONTH

        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Currency": "JPY",
            "Service Provided": f"{STATIC_SERVICE_PROVIDED} (AISPACON)",
            "Region": STATIC_REGION_INFO,
            "GPU ID": f"soroban_aispacon_{num_chips}x_{gpu_variant.replace(' ','_')}",
            "GPU (H100 or H200 or L40S)": base_chip,
            "Memory (GB)": vram,
            "Display Name(GPU Type)": f"{num_chips}x {gpu_variant} (Single Node)",
            "GPU Variant Name": gpu_variant,
            "Amount of Storage": specs.get("ストレージ／ノード", "N/A"),
            "Number of Chips": num_chips,
            "Period": "Per Hour",
            "Total Price ($)": round(total_hourly_price, 4),
            "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_price, 4),
            "Notes / Features": f"Monthly Price: ¥{monthly_price_jpy:,.0f}"
        })
    return data_rows

def _parse_compute_page(soup):
    """ computeページの料金プランテーブルを解析 """
    data_rows = []
    
    header = soup.find(lambda tag: tag.name in ['h2', 'h3'] and "高速コンピューティングの料金プラン" in tag.get_text(strip=True).lower())
    if not header:
        print("ERROR (Soroban Compute): Could not find pricing plan table header.")
        return []

    table = header.find_next('table')
    if not table:
        print("ERROR (Soroban Compute): Could not find pricing table.")
        return []

    # データを列ごとに保持する構造を作成
    rows_data = [row.find_all(['th', 'td']) for row in table.select('tbody > tr')]
    if len(rows_data) < 4: return []
    
    # 最初の列はヘッダーなのでスキップし、各プラン（列）を処理
    for col_idx in range(1, len(rows_data[0])):
        try:
            gpu_spec_str = rows_data[1][col_idx].get_text(strip=True)
            base_chip, gpu_variant, vram, num_chips = _get_gpu_info(gpu_spec_str)

            if not base_chip: continue

            hourly_price_jpy = _parse_price_jp(rows_data[2][col_idx].get_text(strip=True))
            monthly_price_jpy = _parse_price_jp(rows_data[3][col_idx].get_text(strip=True))

            if hourly_price_jpy is None and monthly_price_jpy is None: continue
            
            # 時間料金がない場合は月額から計算
            if hourly_price_jpy is None:
                hourly_price_jpy = monthly_price_jpy / HOURS_IN_MONTH
            
            per_gpu_hourly_price = hourly_price_jpy / num_chips

            data_rows.append({
                "Provider Name": STATIC_PROVIDER_NAME,
                "Currency": "JPY",
                "Service Provided": f"{STATIC_SERVICE_PROVIDED} (Compute)",
                "Region": STATIC_REGION_INFO,
                "GPU ID": f"soroban_compute_{num_chips}x_{gpu_variant.replace(' ','_')}",
                "GPU (H100 or H200 or L40S)": base_chip,
                "Memory (GB)": vram,
                "Display Name(GPU Type)": f"{num_chips}x {gpu_variant}",
                "GPU Variant Name": gpu_variant,
                "Amount of Storage": "100GB+",
                "Number of Chips": num_chips,
                "Period": "Per Hour",
                "Total Price ($)": round(hourly_price_jpy, 4),
                "Effective Hourly Rate ($/hr)": round(per_gpu_hourly_price, 4),
                "Notes / Features": f"Monthly Price available: ¥{monthly_price_jpy:,.0f}" if monthly_price_jpy else ""
            })
        except IndexError:
            continue # 列が存在しない場合はスキップ
            
    return data_rows

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list_jpy = []
    c = CurrencyConverter()

    # --- 1. /aispacon ページの処理 ---
    try:
        print(f"Navigating to Soroban AISPACON: {PRICING_URL_AISPACON}")
        driver.get(PRICING_URL_AISPACON)
        time.sleep(5)

        print("Taking full-page screenshot of Scaleway H100...")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL_AISPACON)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping data from AISPACON page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list_jpy.extend(_parse_aispacon_page(soup))
    except Exception as e:
        print(f"An error occurred during Soroban AISPACON processing: {e}")

    # --- 2. /compute ページの処理 ---
    try:
        print(f"Navigating to Soroban Compute: {PRICING_URL_COMPUTE}")
        driver.get(PRICING_URL_COMPUTE)
        time.sleep(5)

        print("Taking full-page screenshot of Scaleway H100...")
        driver.set_window_size(1920, 800)
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(PRICING_URL_COMPUTE)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping data from Compute page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list_jpy.extend(_parse_compute_page(soup))
    except Exception as e:
        print(f"An error occurred during Soroban Compute processing: {e}")

    # --- 3. 通貨変換処理 (JPY -> USD) ---
    final_data_usd = []
    if scraped_data_list_jpy:
        print(f"Converting {len(scraped_data_list_jpy)} rows from JPY to USD...")
        for data in scraped_data_list_jpy:
            try:
                # 通貨変換が必要なキーの値を変換
                data["Total Price ($)"] = round(c.convert(data["Total Price ($)"], 'JPY', 'USD'), 4)
                data["Effective Hourly Rate ($/hr)"] = round(c.convert(data["Effective Hourly Rate ($/hr)"], 'JPY', 'USD'), 4)
                data["Currency"] = "USD"
                final_data_usd.append(data)
            except Exception as e:
                print(f"Currency conversion failed for row {data.get('GPU ID')}: {e}. Skipping row.")

    return saved_files, final_data_usd