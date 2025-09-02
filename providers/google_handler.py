import time
from bs4 import BeautifulSoup
import re
from datetime import datetime
from PIL import Image
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# --- URL定義 ---
URL_VERTEX_AI = "https://cloud.google.com/vertex-ai/generative-ai/pricing?hl=en"
URL_COMPUTE_GPUS = "https://cloud.google.com/compute/gpus-pricing?hl=en"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Google Cloud"
CHARS_PER_TOKEN_ESTIMATE = 4 # 1トークンあたりの文字数の推定値

def _take_scrolling_screenshot_gcp(driver, filepath):
    """
    Google Cloudのページ特有の内部スクロールと固定ヘッダーに対応した、
    スクロール＆結合スクリーンショットを撮影する。
    """
    print("Taking scrolling screenshot for GCP page...")

    try:
        driver.execute_script("const header = document.querySelector('devsite-header'); if (header) header.style.display = 'none';")
        driver.execute_script("const footer = document.querySelector('devsite-footer'); if (footer) footer.style.display = 'none';")
    except Exception as e:
        print(f"Could not hide header/footer, screenshot may have repeated elements: {e}")

    try:
        driver.set_window_size(1920, 1080)
        time.sleep(2)
        
        scroll_container_selector = "document.querySelector('main.devsite-main-content')"
        total_height = driver.execute_script(f"const el = {scroll_container_selector}; return el ? el.scrollHeight : document.body.parentNode.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        stitched_image = Image.new('RGB', (1920, total_height))
        
        scroll_position = 0
        while scroll_position < total_height:
            driver.execute_script(f"const el = {scroll_container_selector}; if (el) el.scrollTo(0, {scroll_position}); else window.scrollTo(0, {scroll_position});")
            time.sleep(0.5)

            temp_screenshot_path = os.path.join(os.path.dirname(filepath), "temp_screenshot.png")
            driver.save_screenshot(temp_screenshot_path)
            
            screenshot_part = Image.open(temp_screenshot_path)
            
            paste_height = min(viewport_height, total_height - scroll_position)
            screenshot_part = screenshot_part.crop((0, 0, 1920, paste_height))

            stitched_image.paste(screenshot_part, (0, scroll_position))
            
            scroll_position += viewport_height

        stitched_image.save(filepath)
        print(f"Scrolling screenshot saved to: {filepath}")
        
        if os.path.exists(temp_screenshot_path):
            os.remove(temp_screenshot_path)
            
    except Exception as e:
        print(f"Failed to take scrolling screenshot: {e}")
        driver.save_screenshot(filepath)
    finally:
        try:
            driver.execute_script("const header = document.querySelector('devsite-header'); if (header) header.style.display = 'block';")
            driver.execute_script("const footer = document.querySelector('devsite-footer'); if (footer) footer.style.display = 'block';")
        except Exception:
            pass

def create_timestamped_filename(url):
    url_without_query = url.split('?')[0]
    base_name = url_without_query.replace("https://", "").replace("http://", "").replace("www.", "")
    safe_base_name = re.sub(r'[\\/*:"<>|]', '_', base_name).replace('/', '_')
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{safe_base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$0.000125' のような文字列から数値のみを抽出 """
    if not price_str or "Contact sales" in price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            return None
    return None

def _parse_vertex_ai_api(soup):
    """ Vertex AI のAPI料金を解析 """
    api_data = []
    
    # 修正：'Gemini'というテキストを含むh2見出しを探す
    header = soup.find('h2', string=re.compile(r'Gemini'))
    if not header:
        print("ERROR (Google Vertex AI): Could not find 'Gemini' pricing section header.")
        return []
    
    # h2から始まるセクション内の最初のテーブルを探す
    section_container = header.find_parent('div', class_='cloud-section')
    if not section_container:
        section_container = soup # 見つからない場合は全体から探す

    tables = section_container.find_all('table')
    if not tables:
        print("ERROR (Google Vertex AI): Could not find any pricing tables in the section.")
        return []

    # 複数のテーブルを処理
    for table in tables:
        for row in table.select("tbody tr"):
            cols = row.find_all("td")
            if not cols or "Total" in cols[0].get_text(): # 合計行などをスキップ
                continue

            # モデル名や特徴が複数行にまたがる場合があるため前の行から引き継ぐ
            if len(cols) >= 4:
                model_name = cols[0].get_text(strip=True) if cols[0].get_text(strip=True) else model_name
                feature = cols[1].get_text(strip=True) if cols[1].get_text(strip=True) else feature
                input_text = cols[2].get_text(strip=True)
                output_text = cols[3].get_text(strip=True)
            elif len(cols) == 2: # 2列しかない行（前のモデル名を引き継ぐ）
                input_text = cols[0].get_text(strip=True)
                output_text = cols[1].get_text(strip=True)
            else:
                continue

            # --- Input価格の処理 ---
            if (input_price_val := _parse_price(input_text)) is not None:
                period = "Per 1M Tokens"
                price_unit_text = input_text.lower()
                if "character" in price_unit_text:
                    price_per_1k_chars = input_price_val
                    price_per_1k_tokens = price_per_1k_chars * CHARS_PER_TOKEN_ESTIMATE
                    final_price = price_per_1k_tokens * 1000
                elif "image" in price_unit_text:
                    final_price = input_price_val
                    period = "Per Image"
                elif "second" in price_unit_text:
                    final_price = input_price_val * 60 # 分あたりに変換
                    period = "Per Minute"
                elif "hour" in price_unit_text:
                    final_price = input_price_val
                    period = "Per Hour"
                else: # 1M tokens or 1k characters
                    final_price = input_price_val if "token" in price_unit_text else (input_price_val * CHARS_PER_TOKEN_ESTIMATE * 1000)

                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Vertex AI API",
                    "Currency": "USD", "Region": "Multiple",
                    "API_TYPE": f"{model_name} ({feature}) - Input",
                    "GPU (H100 or H200 or L40S)": "", "Period": period,
                    "Total Price ($)": round(final_price, 6),
                })

            # --- Output価格の処理 (Inputと同様) ---
            if (output_price_val := _parse_price(output_text)) is not None:
                period = "Per 1M Tokens"
                price_unit_text = output_text.lower()
                if "character" in price_unit_text:
                    price_per_1k_chars = output_price_val
                    price_per_1k_tokens = price_per_1k_chars * CHARS_PER_TOKEN_ESTIMATE
                    final_price = price_per_1k_tokens * 1000
                elif "hour" in price_unit_text:
                    final_price = output_price_val
                    period = "Per Hour"
                else: # 1M tokens or 1k characters
                    final_price = output_price_val if "token" in price_unit_text else (output_price_val * CHARS_PER_TOKEN_ESTIMATE * 1000)

                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Vertex AI API",
                    "Currency": "USD", "Region": "Multiple",
                    "API_TYPE": f"{model_name} ({feature}) - Output",
                    "GPU (H100 or H200 or L40S)": "", "Period": period,
                    "Total Price ($)": round(final_price, 6),
                })
    return api_data

def _parse_compute_engine_gpu(soup):
    """ Compute Engine のGPUホスティング料金を解析 """
    gpu_data = []
    
    table = soup.select_one("div[data-component='PricingTable'] table")
    if not table: return []
    
    # 現在選択されているリージョンを取得
    region_tag = soup.select_one('.kd-button.kd-dropdown-menu-button--text')
    region = region_tag.get_text(strip=True) if region_tag else "N/A"

    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 3: continue

        gpu_model = cols[0].get_text(strip=True)
        ondemand_price = _parse_price(cols[2].get_text(strip=True))

        if "H100" in gpu_model and ondemand_price is not None:
            gpu_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Compute Engine GPU",
                "Currency": "USD", "Region": region, "GPU ID": f"gcp_{gpu_model.replace(' ','-')}",
                "GPU (H100 or H200 or L40S)": "H100", "GPU Variant Name": "H100 80GB",
                "Display Name(GPU Type)": f"1x {gpu_model}", "Memory (GB)": 80,
                "Number of Chips": 1, "Period": "Per Hour",
                "Total Price ($)": ondemand_price, "Effective Hourly Rate ($/hr)": ondemand_price,
                "API_TYPE": "",
            })
    return gpu_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []

    # --- 1. Vertex AI (API) ---
    try:
        print(f"Navigating to Google Vertex AI Pricing: {URL_VERTEX_AI}")
        driver.get(URL_VERTEX_AI)
        print("Waiting for Vertex AI pricing table to load...")
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Gemini')]"))
            )
            print("Pricing table loaded.")
        except TimeoutException:
            print("WARNING (Google Vertex AI): Timed out waiting for pricing table to load. Scraping may fail.")
        
        time.sleep(3)
        
        filename = create_timestamped_filename(URL_VERTEX_AI)
        filepath = f"{output_directory}/{filename}"
        _take_scrolling_screenshot_gcp(driver, filepath)
        saved_files.append(filepath)

        print("Scraping API data from Vertex AI page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list.extend(_parse_vertex_ai_api(soup))
    except Exception as e:
        print(f"An error occurred during Google Vertex AI processing: {e}")

    # --- 2. Compute Engine (GPUホスティング) ---
    try:
        print(f"Navigating to Google Compute Engine GPU Pricing: {URL_COMPUTE_GPUS}")
        driver.get(URL_COMPUTE_GPUS)

        try:
            # このページは<cloudx-pricing-table>というカスタム要素が読み込まれるのを待つ
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "cloudx-pricing-table"))
            )
            print("Pricing table loaded.")
        except TimeoutException:
            print("WARNING (Google Compute GPU): Timed out waiting for pricing table to load. Scraping may fail.")

        time.sleep(3)
        
        filename = create_timestamped_filename(URL_COMPUTE_GPUS)
        filepath = f"{output_directory}/{filename}"
        _take_scrolling_screenshot_gcp(driver, filepath)
        saved_files.append(filepath)

        print("Scraping GPU hosting data from Compute Engine page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list.extend(_parse_compute_engine_gpu(soup))
    except Exception as e:
        print(f"An error occurred during Google Compute Engine processing: {e}")
        
    return saved_files, scraped_data_list