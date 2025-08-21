import time
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

PRICING_URL = "https://azure.microsoft.com/ja-jp/pricing/details/cognitive-services/openai-service/"

STATIC_PROVIDER_NAME = "Azure"
STATIC_SERVICE_PROVIDED = "Azure OpenAI Service"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price_from_span(span):
    """
    価格情報が含まれるspanタグから、JSONデータを解析して価格を取得する
    """
    if not span or not span.get('data-amount'):
        return None
    try:
        # data-amount属性のJSON文字列を辞書に変換
        amount_data = json.loads(span['data-amount'])
        # "regional" の中の最初の地域の価格を取得する（どの地域でも価格が同じため）
        if "regional" in amount_data and amount_data["regional"]:
            first_region_key = next(iter(amount_data["regional"]))
            return float(amount_data["regional"][first_region_key])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        print(f"Error parsing price data from span: {e}")
        # フォールバックとして表示されているテキストから価格を試みる
        price_text = span.get_text(strip=True)
        match = re.search(r'[\$￥]?([\d\.,]+)', price_text)
        if match:
            try:
                return float(match.group(1).replace(',', ''))
            except ValueError:
                return None
    return None

def _fetch_api_prices(soup):
    final_data = []
    
    # 価格セクション全体を取得
    pricing_section = soup.select_one("section#pricing")
    if not pricing_section:
        print("ERROR (Azure): Pricing section not found.")
        return []

    # モデルカテゴリごと（h2見出しごと）に処理
    model_groups = pricing_section.find_all('h2', recursive=False)
    for group_header in model_groups:
        model_family = group_header.get_text(strip=True)
        
        # h2の次にあるテーブルを探す
        table = group_header.find_next_sibling("div", class_="row").find("table")
        if not table:
            continue
            
        print(f"Processing model family: {model_family}")
        
        # --- 通常の価格テーブルの処理 ---
        for row in table.select("tbody > tr"):
            cols = row.find_all("td")
            if not cols:
                continue

            model_name = cols[0].get_text(strip=True)
            price_cell = cols[1]

            # セル内の価格情報を分割して処理 (例: 入力: $X.XX <br> 出力: $Y.YY)
            # <br>で分割するためにHTML文字列として扱う
            price_lines = str(price_cell).split('<br>')

            for line in price_lines:
                line_soup = BeautifulSoup(line, 'html.parser')
                price_span = line_soup.find("span", class_="price-data")
                if not price_span:
                    continue

                price_type = line_soup.get_text(strip=True).split(':')[0]
                price = _parse_price_from_span(price_span)

                if price is not None:
                    api_type = f"{model_family} - {model_name} - {price_type}"
                    
                    final_data.append({
                        "Provider Name": STATIC_PROVIDER_NAME,
                        "Currency": "USD",
                        "Service Provided": STATIC_SERVICE_PROVIDED,
                        "Region": "Multiple",
                        "API_TYPE": api_type,
                        "GPU (H100 or H200 or L40S)": "",
                        "GPU Variant Name": "N/A",
                        "Number of Chips": "N/A",
                        "Memory (GB)": "N/A",
                        "Amount of Storage": "N/A",
                        "Period": "Per 1M Tokens",
                        "Total Price ($)": price,
                        "Effective Hourly Rate ($/hr)": "N/A",
                    })

    return final_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Azure OpenAI Pricing: {PRICING_URL}")
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
        print(f"An error occurred during Azure processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list