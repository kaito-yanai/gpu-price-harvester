import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://groq.com/pricing"

STATIC_PROVIDER_NAME = "Groq"
CHARS_PER_TOKEN_ESTIMATE = 4 # 1トークンあたりの文字数の推定値

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$0.10' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def _parse_llm_table(soup):
    """ LLMの価格テーブルを解析 """
    llm_data = []
    table = soup.select_one("#pricing-table-llms table")
    if not table: return []

    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 4: continue

        model_name = cols[0].get_text(strip=True)
        input_price = _parse_price(cols[2].get_text(strip=True))
        output_price = _parse_price(cols[3].get_text(strip=True))

        if input_price is not None:
            llm_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "LLM API",
                "Currency": "USD", "API_TYPE": f"{model_name} - Input",
                "Period": "Per 1M Tokens", "Total Price ($)": input_price,
            })
        if output_price is not None:
            llm_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "LLM API",
                "Currency": "USD", "API_TYPE": f"{model_name} - Output",
                "Period": "Per 1M Tokens", "Total Price ($)": output_price,
            })
    return llm_data

def _parse_tts_table(soup):
    """ TTSの価格テーブルを解析 """
    tts_data = []
    table = soup.select_one("#pricing-table-tts table")
    if not table: return []
    
    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 3: continue

        model_name = cols[0].get_text(strip=True)
        price_per_m_chars = _parse_price(cols[2].get_text(strip=True))

        if price_per_m_chars is not None:
            # 100万文字あたりの価格を、100万トークンあたりの価格に推定変換
            price_per_m_tokens = price_per_m_chars * CHARS_PER_TOKEN_ESTIMATE
            
            tts_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "TTS API",
                "Currency": "USD", "API_TYPE": f"{model_name} (TTS)",
                "Period": "Per 1M Tokens (from Chars)", "Total Price ($)": price_per_m_tokens,
                "Notes / Features": f"Original price: ${price_per_m_chars}/1M Chars"
            })
    return tts_data

def _parse_asr_table(soup):
    """ ASRの価格テーブルを解析 """
    asr_data = []
    table = soup.select_one("#pricing-table-asr table")
    if not table: return []
    
    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 3: continue

        model_name = cols[0].get_text(strip=True)
        price_per_hour = _parse_price(cols[2].get_text(strip=True))

        if price_per_hour is not None:
            asr_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "ASR API",
                "Currency": "USD", "API_TYPE": f"{model_name} (ASR)",
                "Period": "Per Hour Transcribed", "Total Price ($)": price_per_hour,
            })
    return asr_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Groq Pricing: {PRICING_URL}")
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
        
        # 各セクションを解析してデータを結合
        scraped_data_list.extend(_parse_llm_table(soup))
        scraped_data_list.extend(_parse_tts_table(soup))
        scraped_data_list.extend(_parse_asr_table(soup))
        
        # APIデータ用のデフォルト値を設定
        for item in scraped_data_list:
            item.setdefault("GPU (H100 or H200 or L40S)", "")
            item.setdefault("GPU Variant Name", "N/A")
            item.setdefault("Number of Chips", "N/A")
            item.setdefault("Effective Hourly Rate ($/hr)", "N/A")
            item.setdefault("Region", "N/A")

    except Exception as e:
        print(f"An error occurred during Groq processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list