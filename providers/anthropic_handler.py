# providers/anthropic_handler.py
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.anthropic.com/pricing#api"

STATIC_PROVIDER_NAME = "Anthropic"
STATIC_SERVICE_PROVIDED = "Claude API"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$15' のような文字列から数値（15.0）を抽出する """
    if not price_str: return None
    match = re.search(r"(\d+\.?\d*)", price_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _parse_model_card(card):
    """
    価格カードからモデル名とInput/Output価格を抽出し、データ行を生成する
    """
    data_rows = []
    model_name_tag = card.select_one("h2.u-display-s")
    if not model_name_tag:
        return []
    
    model_name = model_name_tag.get_text(strip=True)
    
    price_rows = card.select("li.pricing_card_row")
    for row in price_rows:
        price_type_tag = row.select_one(".u-detail-s")
        price_value_tag = row.select_one("span[data-price-full]")

        if price_type_tag and price_value_tag:
            price_type = price_type_tag.get_text(strip=True)
            # "Input" または "Output" を含む行のみを対象
            if "Input" not in price_type and "Output" not in price_type:
                continue

            price_per_mtok = _parse_price(price_value_tag['data-price-full'])

            if price_per_mtok is not None:
                data_rows.append({
                    "Provider Name": STATIC_PROVIDER_NAME,
                    "Currency": "USD",
                    "Service Provided": STATIC_SERVICE_PROVIDED,
                    "Region": "N/A",
                    # 新しいキー: API_TYPE を設定
                    "API_TYPE": f"{model_name} - {price_type}",
                    # 既存のGPU関連キーは空または"N/A"に
                    "GPU (H100 or H200 or L40S)": "",
                    "GPU Variant Name": "N/A",
                    "Number of Chips": "N/A",
                    "Memory (GB)": "N/A",
                    "Amount of Storage": "N/A",
                    # 価格情報を設定
                    "Period": "Per 1M Tokens",
                    "Total Price ($)": price_per_mtok,
                    "Effective Hourly Rate ($/hr)": "N/A",
                })

    return data_rows


def _fetch_api_prices(soup):
    final_data = []
    
    # APIタブのコンテンツ内を探す
    api_tab_content = soup.select_one('div[data-w-tab="API"]')
    if not api_tab_content:
        print("ERROR (Anthropic): API tab content not found.")
        return []

    # --- Latest Models ---
    latest_models_section = api_tab_content.find('h2', string=re.compile("Latest models"))
    if latest_models_section:
        # h2の親要素からカードを探す
        section_wrapper = latest_models_section.find_parent('div')
        cards = section_wrapper.select('li.u-column-4 > div.card')
        print(f"Found {len(cards)} cards in 'Latest models' section.")
        for card in cards:
            final_data.extend(_parse_model_card(card))
            
    # --- Legacy Models ---
    legacy_models_section = api_tab_content.find('h2', string=re.compile("Legacy models"))
    if legacy_models_section:
        section_wrapper = legacy_models_section.find_parent('div')
        cards = section_wrapper.select('li.u-column-3 > div.card') # Legacyは u-column-3
        print(f"Found {len(cards)} cards in 'Legacy models' section.")
        for card in cards:
            final_data.extend(_parse_model_card(card))
            
    return final_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Anthropic Pricing: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5)

        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping API pricing data...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data = _fetch_api_prices(soup)
        if scraped_data:
            scraped_data_list.extend(scraped_data)
        
    except Exception as e:
        print(f"An error occurred during Anthropic processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list