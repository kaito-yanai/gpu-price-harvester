import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

PRICING_URL = "https://www.baseten.co/pricing/"

STATIC_PROVIDER_NAME = "Baseten"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '$0.6312' のような文字列から数値のみを抽出 """
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
    if "h100" in text: return "H100", "H100", 80
    if "b200" in text: return "H200", "B200", 180 # B200をH200カテゴリとして集計
    if "a100" in text: return "H100", "A100", 80 # A100をH100カテゴリとして集計
    if "l40s" in text: return "L40S", "L40S", 48
    return None, None, 0

def _parse_api_section(soup):
    """ Model APIs の価格テーブルを解析 """
    api_data = []
    
    # "Model APIs" のヘッダーを探し、その親からテーブルコンテナを見つける
    header = soup.find('p', string='Model APIs')
    if not header: return []
    
    table_container = header.find_parent('div', class_='mb-8')
    if not table_container: return []
    
    rows = table_container.select("div.grid.relative.grid-cols-3")
    
    # 最初の行はヘッダーなのでスキップ
    for row in rows[1:]:
        cols = row.find_all('div', recursive=False)
        if len(cols) < 3: continue

        model_name = cols[0].get_text(strip=True)
        input_price = _parse_price(cols[1].get_text(strip=True))
        output_price = _parse_price(cols[2].get_text(strip=True))

        if input_price is not None:
            api_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Model APIs",
                "Currency": "USD", "Region": "N/A", "API_TYPE": f"{model_name} - Input",
                "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
                "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
                "Period": "Per 1M Tokens", "Total Price ($)": input_price,
                "Effective Hourly Rate ($/hr)": "N/A",
            })
        if output_price is not None:
            api_data.append({
                "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Model APIs",
                "Currency": "USD", "Region": "N/A", "API_TYPE": f"{model_name} - Output",
                "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
                "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
                "Period": "Per 1M Tokens", "Total Price ($)": output_price,
                "Effective Hourly Rate ($/hr)": "N/A",
            })
            
    return api_data

def _parse_gpu_section(soup):
    """ Dedicated Deployments のGPUホスティング価格を解析 """
    gpu_data = []

    header = soup.find('p', string='Dedicated Deployments')
    if not header: return []

    table_container = header.find_parent('div', class_='mb-8').find_next_sibling('div')
    if not table_container: return []

    rows = table_container.select("div.grid.relative.grid-cols-2")
    
    for row in rows[1:]: # ヘッダー行をスキップ
        cols = row.find_all('div', recursive=False)
        if len(cols) < 2: continue
            
        gpu_name_cell = cols[0].find('p')
        if not gpu_name_cell: continue
            
        gpu_name = gpu_name_cell.get_text(strip=True)
        base_chip, gpu_variant, vram = _get_gpu_info(gpu_name)
        
        if not base_chip: continue

        price = _parse_price(cols[1].get_text(strip=True))
        if price is None: continue
            
        spec_text = cols[0].find('p', class_='text-b-fills-800').get_text(strip=True) if cols[0].find('p', class_='text-b-fills-800') else ""

        gpu_data.append({
            "Provider Name": STATIC_PROVIDER_NAME, "Service Provided": "Dedicated Deployments",
            "Currency": "USD", "Region": "N/A", "GPU ID": f"baseten_{gpu_variant.replace(' ','_')}",
            "GPU (H100 or H200 or L40S)": base_chip, "GPU Variant Name": gpu_variant,
            "Display Name(GPU Type)": f"1x {gpu_variant}", "Memory (GB)": vram,
            "Amount of Storage": "N/A", "Number of Chips": 1, "Period": "Per Hour",
            "Total Price ($)": price, "Effective Hourly Rate ($/hr)": price,
            "API_TYPE": "", "Notes / Features": spec_text,
        })
    return gpu_data

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []
    try:
        print(f"Navigating to Baseten Pricing: {PRICING_URL}")
        driver.get(PRICING_URL)
        time.sleep(5)

        # --- Seleniumで "Hour" ボタンをクリック ---
        try:
            print("Switching GPU pricing to 'Hour'...")
            # "Dedicated Deployments"セクションを特定
            dedicated_header = driver.find_element("xpath", "//p[text()='Dedicated Deployments']")
            section_container = dedicated_header.find_element("xpath", "./ancestor::div[contains(@class, 'mb-8')]")
            
            # そのセクション内の "Hour" ボタンを探してクリック
            hour_button = section_container.find_element("xpath", ".//button[contains(., 'Hour')]")
            driver.execute_script("arguments[0].click();", hour_button)
            print("Successfully switched to hourly pricing.")
            time.sleep(2) # 表示が切り替わるのを待つ
        except Exception as e:
            print(f"Could not switch to hourly pricing, might already be selected or page structure changed: {e}")

        # --- スクリーンショット撮影 ---
        filename = create_timestamped_filename(PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        # --- データ取得 ---
        print("Scraping data from the page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        # APIとGPUの両方のセクションを解析
        scraped_data_list.extend(_parse_api_section(soup))
        scraped_data_list.extend(_parse_gpu_section(soup))
        
    except Exception as e:
        print(f"An error occurred during Baseten processing: {e}")
        import traceback
        traceback.print_exc()

    return saved_files, scraped_data_list