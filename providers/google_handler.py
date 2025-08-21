import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

# --- URL定義 ---
URL_VERTEX_AI = "https://cloud.google.com/vertex-ai/pricing?hl=en"
URL_COMPUTE_GPUS = "https://cloud.google.com/compute/gpus-pricing?hl=en"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "Google Cloud"
CHARS_PER_TOKEN_ESTIMATE = 4 # 1トークンあたりの文字数の推定値

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

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
    
    # "Generative AI models"セクションを探す
    header = soup.find('h2', id='generative-ai-models')
    if not header: return []
    
    # Geminiモデルのテーブルを探す
    table = header.find_next('table')
    if not table: return []

    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 4: continue

        model_name = cols[0].get_text(strip=True)
        feature = cols[1].get_text(strip=True)
        input_text = cols[2].get_text(strip=True)
        output_text = cols[3].get_text(strip=True)

        # --- Input価格の処理 ---
        if input_price_val := _parse_price(input_text):
            period = "Per 1M Tokens"
            if "character" in input_text:
                # 1000文字あたりの価格を100万トークンあたりに変換
                price_per_1k_chars = input_price_val
                price_per_1k_tokens = price_per_1k_chars * CHARS_PER_TOKEN_ESTIMATE
                final_price = price_per_1k_tokens * 1000
            elif "image" in input_text:
                final_price = input_price_val
                period = "Per Image"
            else:
                final_price = input_price_val # その他の単位はそのまま
            
            api_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Vertex AI API",
                "Currency": "USD", "Region": "Multiple",
                "API_TYPE": f"{model_name} ({feature}) - Input",
                "GPU (H100 or H200 or L40S)": "", "Period": period,
                "Total Price ($)": round(final_price, 6),
            })

        # --- Output価格の処理 ---
        if output_price_val := _parse_price(output_text):
            period = "Per 1M Tokens"
            if "character" in output_text:
                price_per_1k_chars = output_price_val
                price_per_1k_tokens = price_per_1k_chars * CHARS_PER_TOKEN_ESTIMATE
                final_price = price_per_1k_tokens * 1000
            elif "image" in output_text:
                final_price = output_price_val
                period = "Per Image"
            else:
                final_price = output_price_val
            
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
        time.sleep(5)
        
        filename = create_timestamped_filename(URL_VERTEX_AI)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
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
        time.sleep(5)
        
        filename = create_timestamped_filename(URL_COMPUTE_GPUS)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping GPU hosting data from Compute Engine page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list.extend(_parse_compute_engine_gpu(soup))
    except Exception as e:
        print(f"An error occurred during Google Compute Engine processing: {e}")
        
    return saved_files, scraped_data_list