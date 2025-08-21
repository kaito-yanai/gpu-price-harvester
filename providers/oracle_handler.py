import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.oracle.com/artificial-intelligence/generative-ai/generative-ai-service/pricing/"

STATIC_PROVIDER_NAME = "Oracle"
STATIC_SERVICE_PROVIDED = "OCI Generative AI"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$3.00' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def _fetch_api_prices(soup):
    """ OCI Generative AI のAPI料金を解析 """
    api_data = []
    
    table = soup.select_one("h4#apex + div table")
    if not table:
        print("ERROR (Oracle): Pricing table not found.")
        return []

    for row in table.select("tbody tr"):
        cols = row.find_all(["th", "td"])
        if len(cols) < 4: continue

        unit_text = cols[3].get_text(strip=True)
        
        # <<< ご指示の通り、単位が "Tokens" の行のみを処理 >>>
        if "tokens" not in unit_text.lower():
            continue

        product_name = cols[0].get_text(strip=True)
        price = _parse_price(cols[2].get_text(strip=True))
        
        if price is None:
            continue
            
        # "Oracle Cloud Infrastructure Generative AI - " の部分を削除してモデル名を整形
        model_name_raw = product_name.replace("Oracle Cloud Infrastructure Generative AI - ", "")
        
        # Input/Output を判定
        price_type = "N/A"
        if "Input Tokens" in model_name_raw:
            price_type = "Input"
            model_name = model_name_raw.replace("- Input Tokens", "").strip()
        elif "Output Tokens" in model_name_raw:
            price_type = "Output"
            model_name = model_name_raw.replace("- Output Tokens", "").strip()
        else:
             model_name = model_name_raw

        api_data.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Service Provided": STATIC_SERVICE_PROVIDED,
            "Currency": "USD",
            "API_TYPE": f"{model_name} - {price_type}",
            "Period": "Per 1M Tokens",
            "Total Price ($)": price,
        })

    return api_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Oracle AI Pricing: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5)

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
            item.setdefault("Region", "N/A")
        
        scraped_data_list.extend(scraped_data)

    except Exception as e:
        print(f"An error occurred during Oracle processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list