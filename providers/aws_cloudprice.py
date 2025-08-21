import time
from bs4 import BeautifulSoup
import re
from datetime import datetime

# --- URL定義 ---
PRICING_URL_EC2 = "https://aws.amazon.com/jp/ec2/capacityblocks/pricing/"
PRICING_URL_SAGEMAKER = "https://aws.amazon.com/jp/sagemaker/pricing/"

# --- 静的情報 ---
STATIC_PROVIDER_NAME = "AWS"

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def _parse_price(price_str):
    """ '12.345 USD' のような文字列から数値のみを抽出 """
    if not price_str: return None
    match = re.search(r'(\d+\.?\d*)', price_str.replace(',', ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def _get_gpu_info(accelerator_str):
    """ '8 x H100' のような文字列から情報を抽出 """
    text = accelerator_str.lower()
    num_chips = 1
    match = re.search(r'(\d+)\s*x', text)
    if match:
        num_chips = int(match.group(1))

    if "h200" in text: return "H200", "H200", 141, num_chips
    if "h100" in text: return "H100", "H100", 80, num_chips
    if "b200" in text: return "H200", "B200", 192, num_chips # B200をH200カテゴリとして集計
    if "a100" in text: return "H100", "A100", 80, num_chips # A100をH100カテゴリとして集計
    
    return None, None, 0, 0

def _parse_ec2_capacity_blocks(soup):
    """ EC2 Capacity Blocks のGPUホスティング料金を解析 """
    data_rows = []
    
    table = soup.select_one("#Pricing_tables + .lb-tbl table")
    if not table:
        print("ERROR (AWS EC2): Could not find the pricing table.")
        return []

    for row in table.select("tbody > tr")[1:]: # ヘッダー行をスキップ
        cols = row.find_all("td")
        if len(cols) < 9: continue

        instance_type = cols[0].get_text(strip=True)
        region = cols[1].get_text(strip=True)
        price_text = cols[2].get_text(strip=True)
        accelerator_text = cols[3].get_text(strip=True)

        base_chip, gpu_variant, vram, num_chips = _get_gpu_info(accelerator_text)
        if not base_chip: continue

        # 価格をインスタンス合計とGPU単価に分解: "31.464 USD (3.933 USD)"
        price_match = re.search(r'([\d\.]+)\s*USD\s*\(?([\d\.]+)\s*USD\)?', price_text.replace(',', ''))
        if not price_match: continue
        
        total_price = float(price_match.group(1))
        per_gpu_price = float(price_match.group(2))
        
        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Service Provided": "EC2 Capacity Blocks",
            "Currency": "USD",
            "Region": region,
            "GPU ID": f"aws_ec2_{instance_type.replace('.','-')}_{region.split(' ')[0]}",
            "GPU (H100 or H200 or L40S)": base_chip,
            "GPU Variant Name": gpu_variant,
            "Display Name(GPU Type)": f"{num_chips}x {gpu_variant} ({instance_type})",
            "Memory (GB)": vram,
            "Amount of Storage": cols[7].get_text(strip=True),
            "Number of Chips": num_chips,
            "Period": "Per Hour",
            "Total Price ($)": total_price,
            "Effective Hourly Rate ($/hr)": per_gpu_price,
            "API_TYPE": "", # GPUホスティングなのでAPI_TYPEは空
        })
    return data_rows

def _parse_sagemaker_api(soup):
    """ SageMaker 料金ページのAPI（レコメンデーション）料金を解析 """
    data_rows = []

    # 「レコメンデーション」の行を探す
    recommendation_row = soup.find('td', string='レコメンデーション')
    if not recommendation_row:
        print("ERROR (AWS SageMaker): Could not find 'Recommendations' pricing row.")
        return []
    
    price_cell = recommendation_row.find_next_sibling('td')
    if not price_cell: return []

    price_text = price_cell.get_text(strip=True)
    
    # "入力トークン 1,000 個あたり 0.015 USD 出力トークン 1,000 個あたり 0.075 USD"
    input_match = re.search(r'入力トークン\s*1,000\s*個あたり\s*([\d\.]+)\s*USD', price_text)
    output_match = re.search(r'出力トークン\s*1,000\s*個あたり\s*([\d\.]+)\s*USD', price_text)

    if input_match:
        price_per_1k = float(input_match.group(1))
        price_per_1m = price_per_1k * 1000
        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Service Provided": "SageMaker API", "Currency": "USD", "Region": "N/A",
            "API_TYPE": "SageMaker Recommendations - Input",
            "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
            "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
            "Period": "Per 1M Tokens", "Total Price ($)": price_per_1m,
            "Effective Hourly Rate ($/hr)": "N/A",
        })

    if output_match:
        price_per_1k = float(output_match.group(1))
        price_per_1m = price_per_1k * 1000
        data_rows.append({
            "Provider Name": STATIC_PROVIDER_NAME,
            "Service Provided": "SageMaker API", "Currency": "USD", "Region": "N/A",
            "API_TYPE": "SageMaker Recommendations - Output",
            "GPU (H100 or H200 or L40S)": "", "GPU Variant Name": "N/A",
            "Number of Chips": "N/A", "Memory (GB)": "N/A", "Amount of Storage": "N/A",
            "Period": "Per 1M Tokens", "Total Price ($)": price_per_1m,
            "Effective Hourly Rate ($/hr)": "N/A",
        })

    return data_rows

def process_data_and_screenshot(driver, output_directory):
    saved_files = []
    scraped_data_list = []

    # --- 1. EC2 Capacity Blocks (GPUホスティング) ---
    try:
        print(f"Navigating to AWS EC2 Capacity Blocks: {PRICING_URL_EC2}")
        driver.get(PRICING_URL_EC2)
        time.sleep(5)
        
        filename = create_timestamped_filename(PRICING_URL_EC2)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping GPU hosting data from EC2 page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list.extend(_parse_ec2_capacity_blocks(soup))
    except Exception as e:
        print(f"An error occurred during AWS EC2 processing: {e}")

    # --- 2. SageMaker (API) ---
    try:
        print(f"Navigating to AWS SageMaker Pricing: {PRICING_URL_SAGEMAKER}")
        driver.get(PRICING_URL_SAGEMAKER)
        time.sleep(5)
        
        filename = create_timestamped_filename(PRICING_URL_SAGEMAKER)
        filepath = f"{output_directory}/{filename}"
        driver.save_screenshot(filepath)
        print(f"Successfully saved screenshot to: {filepath}")
        saved_files.append(filepath)

        print("Scraping API data from SageMaker page...")
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        scraped_data_list.extend(_parse_sagemaker_api(soup))
    except Exception as e:
        print(f"An error occurred during AWS SageMaker processing: {e}")
        
    return saved_files, scraped_data_list