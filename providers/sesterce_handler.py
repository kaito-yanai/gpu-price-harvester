import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

# --- URL定義 ---
PRICING_URL = "https://www.sesterce.com/pricing"
COMPUTE_URL = "https://cloud.sesterce.com/compute"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Sesterce"
STATIC_SERVICE_PROVIDED = "Sesterce GPU Cloud"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$1.7925/hour' のような文字列から数値（1.7925）を抽出する """
    if not price_str: return None
    match = re.search(r"[\$€]?(\d+\.?\d*)", price_str.replace(',', ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _get_gpu_info(gpu_name):
    """ GPU名からカテゴリ、バリアント名、VRAMを返す """
    text = gpu_name.lower()
    if "h200" in text: return "H200", "H200", 141
    if "h100" in text: return "H100", "H100", 80
    if "l40s" in text: return "L40S", "L40S", 48 # L40Sは存在しないが念のため
    if "l40" in text and "l40s" not in text: return "L40S", "L40", 48 # L40をL40Sとして扱う
    return None, None, 0

def _parse_pricing_page(soup):
    """ sesterce.com/pricing ページを解析 """
    data_rows = []
    
    # 各GPUの価格カードを探す
    cards = soup.select("div.sm\\:h-\\[260px\\].p-8")
    print(f"Found {len(cards)} cards on pricing page.")

    for card in cards:
        gpu_name_tag = card.select_one("p.text-lg")
        if not gpu_name_tag: continue
        
        gpu_name = gpu_name_tag.get_text(strip=True)
        base_chip, gpu_variant, vram = _get_gpu_info(gpu_name)
        
        if not base_chip: continue

        specs = {}
        spec_items = card.select("div.flex.items-center.justify-between")
        for item in spec_items:
            key_tag = item.select_one("p:first-child")
            value_tag = item.select_one("p:last-child")
            if key_tag and value_tag:
                key = key_tag.get_text(strip=True).lower()
                specs[key] = value_tag.get_text(strip=True)

        price = _parse_price(specs.get("price", ""))
        if price is None: continue

        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Currency": "USD",
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": "Global", # このページには詳細なリージョン情報なし
            "GPU ID": f"sesterce_pricing_{gpu_variant.replace(' ','_')}",
            "GPU (H100 or H200 or L40S)": base_chip,
            "Memory (GB)": vram,
            "Display Name(GPU Type)": f"1x {gpu_variant}",
            "GPU Variant Name": gpu_variant,
            "Amount of Storage": "N/A",
            "Number of Chips": 1,
            "Period": "Per Hour",
            "Total Price ($)": price,
            "Effective Hourly Rate ($/hr)": price, # 1GPUあたりの価格なので同額
        })
    return data_rows

def _parse_compute_page(soup):
    """ cloud.sesterce.com/compute ページを解析 """
    data_rows = []
    
    # テーブルの各行（dlタグ）を探す
    rows = soup.select("div.pb-4 > dl.group")
    print(f"Found {len(rows)} rows on compute page.")
    
    for row in rows:
        # GPU名とチップ数を取得
        gpu_dt = row.select_one("dt:nth-of-type(1) span")
        if not gpu_dt: continue
        
        gpu_name_raw = gpu_dt.get_text(strip=True)
        num_chips_raw = gpu_dt.select_one("span.text-xs").get_text(strip=True) if gpu_dt.select_one("span.text-xs") else "1x"
        
        gpu_name = gpu_name_raw.replace(num_chips_raw, "").strip()
        num_chips = int(re.search(r'(\d+)', num_chips_raw).group(1)) if re.search(r'(\d+)', num_chips_raw) else 1

        base_chip, gpu_variant, vram = _get_gpu_info(gpu_name)
        if not base_chip: continue

        # 価格を取得
        price_dt = row.select_one("dt:last-of-type a")
        if not price_dt: continue
        
        total_price = _parse_price(price_dt.get_text(strip=True))
        if total_price is None: continue
        
        per_gpu_price = total_price / num_chips

        # --- リージョン情報の抽出 ---
        region_dt = row.select_one("dt:nth-of-type(5)")
        region_text = "Global"
        if region_dt:
            flags = region_dt.select("img[title]")
            country_codes = sorted(list(set([flag['title'] for flag in flags])))
            
            plus_button = region_dt.select_one("button")
            hidden_count = 0
            if plus_button and "+" in plus_button.get_text():
                hidden_count = int(re.search(r'(\d+)', plus_button.get_text()).group(1))
            
            total_regions = len(country_codes) + hidden_count
            
            if total_regions > 0:
                examples = ", ".join(country_codes[:3])
                region_text = f"{total_regions}+ Global (e.g. {examples})"

        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Currency": "USD",
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Region": region_text,
            "GPU ID": f"sesterce_compute_{num_chips}x_{gpu_variant.replace(' ','_')}",
            "GPU (H100 or H200 or L40S)": base_chip,
            "Memory (GB)": vram,
            "Display Name(GPU Type)": f"{num_chips}x {gpu_variant}",
            "GPU Variant Name": gpu_variant,
            "Amount of Storage": "N/A",
            "Number of Chips": num_chips,
            "Period": "Per Hour",
            "Total Price ($)": round(total_price, 4),
            "Effective Hourly Rate ($/hr)": round(per_gpu_price, 4),
        })
    return data_rows

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []

    # --- 1. /pricing ページの処理 ---
    try:
        print(f"Navigating to Sesterce Pricing: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping data from pricing page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _parse_pricing_page(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)
    except Exception as e:
        print(f"An error occurred during Sesterce pricing page processing: {e}")

    # --- 2. /compute ページの処理 ---
    try:
        print(f"Navigating to Sesterce Compute: {COMPUTE_URL}")
        driver.get(COMPUTE_URL)
        time.sleep(5)

        filename = create_timestamped_filename(COMPUTE_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping data from compute page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data = _parse_compute_page(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)
    except Exception as e:
        print(f"An error occurred during Sesterce compute page processing: {e}")
        
    return saved_files, scraped_data_list