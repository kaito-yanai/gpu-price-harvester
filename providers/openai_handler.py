import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://openai.com/ja-JP/api/pricing/"

STATIC_PROVIDER_NAME = "OpenAI"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$1.250 / 100万トークン' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def _parse_cards_section(soup, section_header_text):
    """
    「フラッグシップモデル」や「ファインチューニング」のようなカード型セクションを解析
    """
    data = []
    header = soup.find('h2', string=section_header_text)
    if not header:
        header = soup.find('h3', string=section_header_text)
    if not header:
        print(f"WARNING (OpenAI): Could not find section header '{section_header_text}'.")
        return []
    
    # h2/h3から最も近い親のsectionを探し、その中のカードを全て取得
    section_container = header.find_parent('section')
    if not section_container: return []
    
    cards = section_container.select("div.border.p-md")
    for card in cards:
        model_name_tag = card.select_one("h2.text-h4")
        if not model_name_tag: continue
        
        model_name = model_name_tag.get_text(strip=True)
        
        price_items = card.find_all(string=re.compile(r' / 100万トークン'))
        for item in price_items:
            price_text = item.strip()
            price = _parse_price(price_text)
            price_type = price_text.split('：')[0].strip() # "入力：" -> "入力"

            if price is not None:
                api_type_prefix = f"{model_name}"
                if "ファインチューニング" in section_header_text:
                    api_type_prefix += " - Fine-tuning"

                data.append({
                    "Provider Name": STATIC_PROVIDER_NAME,
                    "Service Provided": "OpenAI API",
                    "Currency": "USD",
                    "API_TYPE": f"{api_type_prefix} - {price_type}",
                    "Period": "Per 1M Tokens",
                    "Total Price ($)": price,
                })
    return data

def _parse_our_api_section(soup):
    """
    「当社 API」セクションのテーブル型レイアウトを解析
    """
    data = []
    header = soup.find('h2', string='当社 API')
    if not header:
        print("WARNING (OpenAI): Could not find '当社 API' section.")
        return []

    section_container = header.find_parent('section')
    if not section_container: return []
    
    # Realtime API と Image Generation API のコンテナを処理
    api_boxes = section_container.select("div.border.p-md")
    for box in api_boxes:
        api_name_tag = box.select_one("h2.text-h4")
        if not api_name_tag: continue
        api_name = api_name_tag.get_text(strip=True)

        # モダリティ（テキスト、音声、画像）ごとに処理
        modality_buttons = box.select("button h3.text-p2")
        for button in modality_buttons:
            modality_name = button.get_text(strip=True)
            
            # 各モデルの価格行を取得
            # 構造が複雑なため、ボタンの親要素から辿る
            price_container = button.find_parent("div", class_="@md:hidden").find_next_sibling("div", class_="@md:block")
            if not price_container: continue

            model_rows = price_container.select("div.@md\\:grid")
            for row in model_rows:
                # デスクトップ表示用の要素から情報を取得
                desktop_cols = row.select("div.@md\\:grid > div")
                if len(desktop_cols) < 2: continue
                
                model_name = desktop_cols[0].get_text(strip=True)
                
                # 入力、キャッシュ、出力の価格をそれぞれ取得
                for i in range(1, len(desktop_cols)):
                    price_text = desktop_cols[i].get_text(strip=True)
                    price = _parse_price(price_text)
                    
                    price_type_raw = price_text.split('/')[0].strip()
                    if "入力" in price_type_raw: price_type = "Input"
                    elif "キャッシュ" in price_type_raw: price_type = "Cached Input"
                    elif "出力" in price_type_raw: price_type = "Output"
                    else: continue

                    if price is not None:
                        data.append({
                            "Provider Name": STATIC_PROVIDER_NAME,
                            "Service Provided": "OpenAI API",
                            "Currency": "USD",
                            "API_TYPE": f"{api_name} - {modality_name} - {model_name} - {price_type}",
                            "Period": "Per 1M Tokens",
                            "Total Price ($)": price,
                        })

    return data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to OpenAI Pricing: {PRICING_URL}")
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

        print("Scraping data from the page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        # 各セクションを解析してデータを結合
        scraped_data_list.extend(_parse_cards_section(soup, "フラッグシップモデル"))
        scraped_data_list.extend(_parse_cards_section(soup, "当社モデルのファインチューニング"))
        scraped_data_list.extend(_parse_our_api_section(soup))
        
        # APIデータ用のデフォルト値を設定
        for item in scraped_data_list:
            item.setdefault("GPU (H100 or H200 or L40S)", "")
            item.setdefault("GPU Variant Name", "N/A")
            item.setdefault("Number of Chips", "N/A")
            item.setdefault("Effective Hourly Rate ($/hr)", "N/A")
            item.setdefault("Region", "N/A")

    except Exception as e:
        print(f"An error occurred during OpenAI processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list