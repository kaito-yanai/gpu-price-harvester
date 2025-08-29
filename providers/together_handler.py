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
    
    # "Serverless Inference" という見出しを探す
    header = soup.find('h2', string='Serverless Inference')
    if not header:
        print("ERROR (Together AI): Could not find 'Serverless Inference' header.")
        return []

    # 見出しの親セクションからテーブルを探す
    parent_section = header.find_parent('div', class_='pricing_body-box')
    if not parent_section:
        print("ERROR (Together AI): Could not find parent section for the table.")
        return []
    
    table = parent_section.find('table')
    if not table:
        print("ERROR (Together AI): Could not find the pricing table.")
        return []

    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        # 1列目: モデル名
        model_name_tag = cols[0].select_one("p.text-weight-medium")
        if not model_name_tag:
            continue
        model_name = model_name_tag.get_text(strip=True)

        # 2列目: Input価格
        input_price = _parse_price(cols[1].get_text(strip=True))
        
        # 3列目: Output価格
        output_price = _parse_price(cols[2].get_text(strip=True))
        
        if input_price is not None:
            api_data.append({
                "Provider Name": STATIC_PROVIDER_NAME,
                "Service Provided": "Serverless API",
                "Currency": "USD",
                "API_TYPE": f"{model_name} - Input",
                "Period": "Per 1M Tokens",
                "Total Price ($)": input_price
            })

        if output_price is not None:
            api_data.append({
                "Provider Name": STATIC_PROVIDER_NAME,
                "Service Provided": "Serverless API",
                "Currency": "USD",
                "API_TYPE": f"{model_name} - Output",
                "Period": "Per 1M Tokens",
                "Total Price ($)": output_price
            })

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