# providers/anthropic_handler.py
import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.anthropic.com/pricing#api"

STATIC_PROVIDER_NAME = "Anthropic"
STATIC_SERVICE_PROVIDED = "Claude API"

def create_timestamped_filename(url):
    url_without_query = url.split('#')[0]
    base_name = url_without_query.replace("https://", "").replace("http://", "").replace("www.", "")
    safe_base_name = re.sub(r'[\\/*:"<>|]', '_', base_name).replace('/', '_')
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{safe_base_name}_{timestamp}.png"

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
    print(model_name_tag)
    if not model_name_tag:
        return []
    
    model_name = model_name_tag.get_text(strip=True)
    
    # pricing_card_row ごとにループ
    price_rows = card.select("li.pricing_card_row")
    for row in price_rows:
        # まず、行全体から "Input" か "Output" を特定する
        row_text = row.get_text()
        io_type = ""
        if "Input" in row_text and "Output" not in row_text:
            io_type = "Input"
        elif "Output" in row_text:
            io_type = "Output"
        else:
            continue # Input/Output以外の行はスキップ

        # 価格情報が含まれるすべてのspanタグを取得
        price_spans = row.select("span[data-price-full]")
        # 価格の説明文を取得（Sonnetのような階層価格で使用）
        price_tier_descriptions = row.select(".u-detail-s.u-flex-grow")

        if len(price_spans) == 1:
            # シンプルな価格構造 (Opus, Haiku)
            price_per_mtok = _parse_price(price_spans[0]['data-price-full'])
            if price_per_mtok is not None:
                data_rows.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Currency": "USD",
                    "Service Provided": STATIC_SERVICE_PROVIDED, "Region": "N/A",
                    "API_TYPE": f"{model_name} - {io_type}",
                    "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
                    "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
                    "Period": "Per 1M Tokens", "Total Price ($)": price_per_mtok,
                    "Effective Hourly Rate ($/hr)": "N/A",
                })
        elif len(price_spans) > 1:
            # 複雑な(階層的な)価格構造 (Sonnet)
            for i, span in enumerate(price_spans):
                price_per_mtok = _parse_price(span['data-price-full'])
                # 対応する説明文を取得。なければ汎用的なテキスト
                tier_desc = price_tier_descriptions[i].get_text(strip=True) if i < len(price_tier_descriptions) else ""
                
                if price_per_mtok is not None:
                    data_rows.append({
                        "Provider Name": STATIC_PROVIDER_NAME, "Currency": "USD",
                        "Service Provided": STATIC_SERVICE_PROVIDED, "Region": "N/A",
                        "API_TYPE": f"{model_name} - {io_type} ({tier_desc})",
                        "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
                        "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
                        "Period": "Per 1M Tokens", "Total Price ($)": price_per_mtok,
                        "Effective Hourly Rate ($/hr)": "N/A",
                    })

    return data_rows


def _fetch_api_prices(soup):
    final_data = []
    
    # APIタブのコンテンツ内を探す
    api_tab_content = soup.body
    if not api_tab_content:
        print("ERROR (Anthropic): API tab content not found.")
        return []

    # --- Latest Models ---
    latest_models_section = None
    all_h2_tags = soup.find_all('h2')
    for h2_tag in all_h2_tags:
        # .get_text()は<br>などを無視してテキストを連結してくれる
        if "Latest models" in h2_tag.get_text():
            latest_models_section = h2_tag
            break # 見つかったらループを抜ける
    if latest_models_section:
        # h2の次にあるul要素（カードリスト）を探す
        card_list_ul = latest_models_section.find_next('ul', class_='u-grid-desktop')
        if card_list_ul:
            cards = card_list_ul.select('li.u-column-4 > div.card')
            print(f"Found {len(cards)} cards in 'Latest models' section.")
            for card in cards:
                final_data.extend(_parse_model_card(card))
        else:
            print("ERROR (Anthropic): Could not find the card list (ul) for 'Latest models'.")
    else:
        print("ERROR (Anthropic): Could not find 'Latest models' h2 header.")
            
    return final_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Anthropic Pricing: {PRICING_URL}")
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