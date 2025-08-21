import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://cloud.sambanova.ai/plans/pricing"

STATIC_PROVIDER_NAME = "SambaNova"
STATIC_SERVICE_PROVIDED = "SambaNova API"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$0.10' や '$0.10 input audio...' のような文字列から数値のみを抽出 """
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
    
    data_grid = soup.select_one("div.MuiDataGrid-root")
    if not data_grid:
        print("ERROR (SambaNova): Could not find the data grid.")
        return []

    current_group = ""
    rows = data_grid.select("div.MuiDataGrid-row")

    for row in rows:
        # グループヘッダー行の場合、現在のグループ名を更新
        if 'group-header' in row.get('class', []):
            group_tag = row.select_one("h6.MuiTypography-subtitle2")
            if group_tag:
                current_group = group_tag.get_text(strip=True)
            continue

        # モデルアイテム行の場合、データを抽出
        if 'group-item' in row.get('class', []):
            model_cell = row.select_one('[data-field="model_name"]')
            input_cell = row.select_one('[data-field="input_token_price"]')
            output_cell = row.select_one('[data-field="output_token_price"]')

            if not all([model_cell, input_cell, output_cell]):
                continue

            model_name = model_cell.get_text(strip=True)
            input_text = input_cell.get_text(strip=True)
            output_text = output_cell.get_text(strip=True)

            input_price = _parse_price(input_text)
            output_price = _parse_price(output_text)

            # ASRモデル (Whisper) のような時間単位の価格を特別処理
            if "per hour" in input_text.lower():
                if input_price is not None:
                    api_data.append({
                        "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Currency": "USD", "API_TYPE": f"{current_group} - {model_name} (ASR)",
                        "Period": "Per Hour Transcribed", "Total Price ($)": input_price,
                    })
            else:
                # 通常のトークン単位の価格
                if input_price is not None:
                    api_data.append({
                        "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Currency": "USD", "API_TYPE": f"{current_group} - {model_name} - Input",
                        "Period": "Per 1M Tokens", "Total Price ($)": input_price,
                    })
                if output_price is not None:
                     api_data.append({
                        "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Currency": "USD", "API_TYPE": f"{current_group} - {model_name} - Output",
                        "Period": "Per 1M Tokens", "Total Price ($)": output_price,
                    })

    return api_data


def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to SambaNova Pricing: {PRICING_URL}")
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
        print(f"An error occurred during SambaNova processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list