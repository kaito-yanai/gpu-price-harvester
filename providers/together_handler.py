import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.together.ai/pricing"

STATIC_PROVIDER_NAME = "Together AI"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    if not price_str: return None
    match = re.search(r'[\$]?([\d\.,]+)', price_str)
    if match:
        try:
            return float(match.group(1).replace(',', '').replace(':', '.')) # "2:40" -> 2.40
        except ValueError:
            return None
    return None

def _get_gpu_info(gpu_str):
    text = gpu_str.lower()
    if "h200" in text: return "H200", "H200", 141
    if "h100" in text: return "H100", "H100", 80
    if "a100" in text: return "H100", "A100", 80 # A100をH100カテゴリとして集計
    if "l40s" in text: return "L40S", "L40S", 48
    return None, None, 0

def _parse_api_section(soup):
    api_data = []
    
    # "Serverless Endpoints" セクション内の価格リストを探す
    serverless_section = soup.find('div', id='inference')
    if not serverless_section: return []
    
    pricing_items = serverless_section.find_next('ul', class_='pricing-list').find_all('li', class_='pricing_item', recursive=False)
    
    for item in pricing_items:
        header_text = item.select_one(".pricing_head h3").get_text(strip=True)
        
        # ご指示通り、トークン単位以外のAPIはスキップ
        if "image" in header_text.lower() or "audio" in header_text.lower():
            continue

        rows = item.select(".pricing_content li.pricing_content-row")
        for row in rows[1:]: # ヘッダー行をスキップ
            cells = row.select(".pricing_content-cell")
            if not cells: continue

            model_name = cells[0].get_text(strip=True)
            price_text = cells[-1].get_text(strip=True) # 価格は常に最後のセルにあると仮定
            price = _parse_price(price_text)
            
            # Input/Output分離型
            if "input" in price_text.lower() and "output" in price_text.lower():
                input_match = re.search(r'([\d\.]+)\s*input', price_text, re.I)
                output_match = re.search(r'([\d\.]+)\s*output', price_text, re.I)
                if input_match:
                    api_data.append({"Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API", "Currency": "USD", "API_TYPE": f"{model_name} - Input", "Period": "Per 1M Tokens", "Total Price ($)": _parse_price(input_match.group(1))})
                if output_match:
                    api_data.append({"Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API", "Currency": "USD", "API_TYPE": f"{model_name} - Output", "Period": "Per 1M Tokens", "Total Price ($)": _parse_price(output_match.group(1))})
            # 単一価格
            elif price is not None:
                api_data.append({"Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Serverless API", "Currency": "USD", "API_TYPE": model_name, "Period": "Per 1M Tokens", "Total Price ($)": price})

    return api_data

def _parse_gpu_section(soup):
    gpu_data = []
    
    # "Dedicated endpoints" と "GPU Clusters" の両方を対象
    sections_to_check = ["dedicated", "gpu-clusters"]
    for section_id in sections_to_check:
        section = soup.find('div', id=section_id)
        if not section: continue
        
        list_container = section.find_next("ul", class_="pricing-list")
        if not list_container:
            list_container = section.find_next("div", class_="pricing_content")
        if not list_container: continue

        rows = list_container.select("li.pricing_content-row")
        for row in rows[1:]: # ヘッダー行をスキップ
            cells = row.select(".pricing_content-cell, .pricing_content-cell-copy")
            if len(cells) < 3: continue

            gpu_name_raw = cells[0].get_text(strip=True)
            # Price/hour は3番目のセル
            price_per_hour = _parse_price(cells[2].get_text(strip=True))
            
            base_chip, gpu_variant, vram = _get_gpu_info(gpu_name_raw)

            if base_chip and price_per_hour is not None:
                gpu_data.append({
                    "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Dedicated GPU",
                    "Currency": "USD", "Region": "N/A", "GPU ID": f"together_{gpu_variant.replace(' ','_')}",
                    "GPU (H100 or H200 or L40S)": base_chip, "GPU Variant Name": gpu_variant,
                    "Display Name(GPU Type)": f"1x {gpu_variant}", "Memory (GB)": vram,
                    "Number of Chips": 1, "Period": "Per Hour",
                    "Total Price ($)": price_per_hour, "Effective Hourly Rate ($/hr)": price_per_hour, "API_TYPE": ""
                })
    return gpu_data


def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Together AI Pricing: {PRICING_URL}")
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
        
        # APIとGPUの両方のセクションを解析
        scraped_data_list.extend(_parse_api_section(soup))
        scraped_data_list.extend(_parse_gpu_section(soup))
        
        # 取得したデータにデフォルト値を設定
        for item in scraped_data_list:
            item.setdefault("GPU (H100 or H200 or L40S)", "")
            item.setdefault("GPU Variant Name", "N/A")
            item.setdefault("Number of Chips", "N/A")
            item.setdefault("Effective Hourly Rate ($/hr)", "N/A")
            item.setdefault("Region", "N/A")
            item.setdefault("API_TYPE", "")

    except Exception as e:
        print(f"An error occurred during Together AI processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list