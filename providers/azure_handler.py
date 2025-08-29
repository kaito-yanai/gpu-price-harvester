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
    model_groups = pricing_section.find_all('div', class_='row column', recursive=False)
    for group_container in model_groups:
        group_header = group_container.find('h2')
        table = group_container.find("table")

        # h2（見出し）とtable（価格表）が両方存在するセクションのみを対象
        if not group_header or not table:
            continue
        
        model_family = group_header.get_text(strip=True)
        print(f"Processing model family: {model_family}")
        
        for row in table.select("tbody > tr"):
            cols = row.find_all("td")
            if not cols:
                continue

            model_name = cols[0].get_text(strip=True).replace('\n', ' ').strip()
            # 結合されたセル（rowspan）の場合、モデル名を前の行から引き継ぐ
            if row.td.get('rowspan'):
                main_model_name = model_name
            elif not row.find('td', attrs={'rowspan': True}):
                # rowspanを持つtdが無い場合、main_model_name を更新する
                if 'main_model_name' not in locals() or len(cols) > 1 :
                    main_model_name = model_name

            price_cell_index = -1 # 価格情報は最後のセルにあることが多い
            price_cell = cols[price_cell_index]

            # セル内のテキストノードとspanタグを順番に処理し、価格情報を抽出する
            price_type = " "
            for content in price_cell.contents:
                if isinstance(content, str) and content.strip():
                    # "入力:", "出力:", "オーディオ" などのテキストを取得
                    cleaned_text = content.strip().replace(':', '').strip()
                    if cleaned_text:
                        price_type = cleaned_text
                
                elif content.name == 'span' and 'price-data' in content.get('class', []):
                    price = _parse_price_from_span(content)
                    if price is not None:
                        # モデル名が複数行にまたがる場合を考慮
                        full_model_name = f"{main_model_name} - {model_name}" if main_model_name != model_name else main_model_name
                        api_type = f"{model_family} - {full_model_name} - {price_type}"

                        # 単位（/時間など）を取得
                        unit_text = content.next_sibling
                        period = "Per 1M Tokens" # デフォルト
                        if unit_text and isinstance(unit_text, str):
                            if "時間" in unit_text:
                                period = "Per Hour"
                            elif "画像" in unit_text:
                                period = "Per 100 Images"

                        final_data.append({
                            "Provider Name": STATIC_PROVIDER_NAME, "Currency": "USD",
                            "Service Provided": STATIC_SERVICE_PROVIDED, "Region": "Multiple",
                            "API_TYPE": api_type.strip(),
                            "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
                            "Number of Chips": "N/A", "Memory (GB)": "N/A",
                            "Amount of Storage": "N/A",
                            "Period": period,
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
        print(f"An error occurred during Azure processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list