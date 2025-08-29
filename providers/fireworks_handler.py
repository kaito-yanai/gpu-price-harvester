import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://fireworks.ai/pricing"

STATIC_PROVIDER_NAME = "Fireworks AI"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$2.90' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'[\$]?(\d+\.?\d*)', price_str.replace(',', ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _get_gpu_info(gpu_name):
    """ GPU名からカテゴリ、バリアント名、VRAMを返す """
    text = gpu_name.lower()
    if "h200" in text: return "H200", "H200", 141
    if "h100" in text: return "H100", "H100", 80
    if "b200" in text: return "H200", "B200", 180 # B200をH200カテゴリとして集計
    if "a100" in text: return "H100", "A100", 80 # A100をH100カテゴリとして集計
    # このページにL40Sはないが、念のため
    if "l40s" in text: return "L40S", "L40S", 48
    return None, None, 0

def _parse_api_section(soup):
    """ Serverless Pricing (API) のテーブルを解析 """
    api_data = []
    
    header = soup.find('h2', string='Text and Vision')
    if not header: return []
    
    table = header.find_next_sibling('table')
    if not table: return []

    for row in table.select("tbody > tr"):
        cols = row.find_all("td")
        if len(cols) < 2: continue
            
        model_name = cols[0].get_text(strip=True)
        price_text = cols[1].get_text(strip=True)

        # 価格が input/output で分かれているかチェック
        if "input" in price_text.lower() and "output" in price_text.lower():
            input_match = re.search(r'([\d\.]+)\s*input', price_text, re.IGNORECASE)
            output_match = re.search(r'([\d\.]+)\s*output', price_text, re.IGNORECASE)
            
            if input_match:
                price = _parse_price(input_match.group(1))
                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API",
                    "Currency": "USD", "Region": "N/A", "API_TYPE": f"{model_name} - Input",
                    "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A", "Number of Chips": "N/A",
                    "Period": "Per 1M Tokens", "Total Price ($)": price, "Effective Hourly Rate ($/hr)": "N/A",
                })
            if output_match:
                price = _parse_price(output_match.group(1))
                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API",
                    "Currency": "USD", "Region": "N/A", "API_TYPE": f"{model_name} - Output",
                    "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A", "Number of Chips": "N/A",
                    "Period": "Per 1M Tokens", "Total Price ($)": price, "Effective Hourly Rate ($/hr)": "N/A",
                })
        else:
            # 統一価格の場合
            price = _parse_price(price_text)
            if price is not None:
                api_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API",
                    "Currency": "USD", "Region": "N/A", "API_TYPE": f"{model_name}",
                    "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A", "Number of Chips": "N/A",
                    "Period": "Per 1M Tokens", "Total Price ($)": price, "Effective Hourly Rate ($/hr)": "N/A",
                })
    return api_data

def _parse_gpu_section(soup):
    """ On-Demand Pricing (GPU) のテーブルを解析 """
    gpu_data = []
    
    header = soup.find('h2', string='On demand deployments')
    if not header: return []

    table = header.find_next_sibling('table')
    if not table: return []

    for row in table.select("tbody > tr"):
        cols = row.find_all("td")
        if len(cols) < 2: continue

        gpu_name = cols[0].get_text(strip=True)
        price = _parse_price(cols[1].get_text(strip=True))
        
        base_chip, gpu_variant, vram = _get_gpu_info(gpu_name)
        if not base_chip or price is None:
            continue

        gpu_data.append({
            "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "On-Demand GPU",
            "Currency": "USD", "Region": "N/A", "GPU ID": f"fireworks_{gpu_variant.replace(' ','_')}",
            "GPU (H100 or H200 or L40S)": base_chip, "GPU Variant Name": gpu_variant,
            "Display Name(GPU Type)": f"1x {gpu_variant}", "Memory (GB)": vram,
            "Number of Chips": 1, "Period": "Per Hour",
            "Total Price ($)": price, "Effective Hourly Rate ($/hr)": price,
            "API_TYPE": "",
        })
    return gpu_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Fireworks AI Pricing: {PRICING_URL}")
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
        
        # APIとGPUの両方のセクションを解析
        scraped_data_list.extend(_parse_api_section(soup))
        scraped_data_list.extend(_parse_gpu_section(soup))
        
    except Exception as e:
        print(f"An error occurred during Fireworks AI processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list