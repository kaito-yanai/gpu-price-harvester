import requests
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone
import time

RUNPOD_PRICING_URL = "https://www.runpod.io/pricing"
HOURS_IN_MONTH = 730 # Maintained for consistency, though not used for price calculation

# --- Static text and helper functions remain largely the same ---
STATIC_SERVICE_PROVIDED_RUNPOD = "AI-specialized cloud (RunPod)"
STATIC_REGION_INFO_RUNPOD = "30+ Global (e.g. US-CA-1, EU-IS-1, AP-SG-1)"
STATIC_STORAGE_OPTION_RUNPOD = "Local NVMe SSD + Network Volume" # Simplified based on general knowledge
STATIC_AMOUNT_OF_STORAGE_RUNPOD = "Varies by instance"
STATIC_NETWORK_PERFORMANCE_RUNPOD = "Varies (e.g., up to 3.2 Tbps Inter-Pod)"

def get_canonical_variant_and_base_chip(gpu_id, display_name):
    text_to_search = (str(gpu_id) + " " + str(display_name)).lower()
    # This map remains crucial for categorization
    variant_map = {
        "H100 SXM": (["h100 sxm"], "H100"), "H100 NVL": (["h100 nvl"], "H100"),
        "H100 PCIe": (["h100 pcie"], "H100"),
        "H200 SXM": (["h200 sxm"], "H200"), "GH200 SXM": (["gh200 sxm"], "H200"),
        "H200 NVL": (["h200 nvl"], "H200"), "GH200 NVL": (["gh200 nvl"], "H200"),
        "L40S": (["l40s"], "L40S"),
    }
    for canonical, (terms, family) in variant_map.items():
        if all(term in text_to_search for term in terms): return canonical, family
    if "l40s" in text_to_search or "l40 s" in text_to_search : return display_name, "L40S"
    if "h100" in text_to_search: return display_name, "H100"
    if "gh200" in text_to_search or "h200" in text_to_search: return display_name, "H200"
    # Fallback for other models we might want to track
    if "l40" in text_to_search: return display_name, "L40S" # General L40S category
    return None, None

def fetch_runpod_data(soup):
    final_sheet_rows_unpivoted = []
    provider_name_for_sheet = "RunPod"

    print("RunPod Handler: Switched to new scraping method for visible HTML.")

    # --- NEW: Scrape visible HTML as __NEXT_DATA__ is no longer available ---
    gpu_rows = soup.select('.gpu-pricing-table__list .gpu-pricing-row')
    if not gpu_rows:
        print("ERROR (RunPod): Could not find '.gpu-pricing-row' elements. The HTML structure may have changed again.")
        return []

    print(f"Found {len(gpu_rows)} RunPod offerings in the new HTML structure.")

    for row in gpu_rows:
        try:
            display_name_tag = row.select_one('.gpu-pricing-row__model-wrapper .text-block-2')
            display_name_from_runpod = display_name_tag.get_text(strip=True) if display_name_tag else "N/A"

            # Use the display name as the primary ID now
            gpu_id_from_runpod = display_name_from_runpod
            
            canonical_variant_name, base_chip_category = get_canonical_variant_and_base_chip(gpu_id_from_runpod, display_name_from_runpod)

            # Filter for only the GPU families we are interested in
            if not base_chip_category:
                continue

            # --- Extract Specs ---
            specs = {"vram": 0, "ram": 0, "vcpu": 0}
            tags = row.select('.gpu-pricing-row__tag')
            for tag in tags:
                text = tag.get_text(separator=' ', strip=True).lower()
                value_match = re.search(r'(\d+)', text)
                value = int(value_match.group(1)) if value_match else 0
                
                if 'vram' in text:
                    specs['vram'] = value
                elif 'ram' in text:
                    specs['ram'] = value
                elif 'vcpu' in text:
                    specs['vcpu'] = value
            
            # --- Extract Price ---
            price_tag = row.select_one('.cc-gpu-price')
            if not price_tag:
                continue

            # The old script used "securePrice". We will use the corresponding "data-secure-cloud-price"
            # Community cloud price is available but we will stick to secure for consistency
            secure_price_str = price_tag.get('data-secure-cloud-price')
            
            try:
                base_1x_hourly_price = float(secure_price_str) if secure_price_str else None
            except (ValueError, TypeError):
                base_1x_hourly_price = None

            if base_1x_hourly_price is None:
                continue # Skip if there's no valid price

            # --- IMPORTANT: Commitment prices are no longer on this page ---
            # All commitment-related fields will be marked "N/A"
            one_month_discount_hourly = "N/A"
            three_month_discount_hourly = "N/A"
            six_month_discount_hourly = "N/A"
            twelve_month_discount_hourly = "N/A"
            
            base_info_for_row = {
                "Provider Name": provider_name_for_sheet,
                "Currency": "USD",
                "Service Provided": STATIC_SERVICE_PROVIDED_RUNPOD,
                "Region": STATIC_REGION_INFO_RUNPOD,
                "GPU ID": gpu_id_from_runpod,
                "GPU (H100 or H200 or L40S)": base_chip_category,
                "Memory (GB)": specs['vram'],
                "Display Name(GPU Type)": display_name_from_runpod,
                "GPU Variant Name": canonical_variant_name,
                "Storage Option": STATIC_STORAGE_OPTION_RUNPOD,
                "Amount of Storage": STATIC_AMOUNT_OF_STORAGE_RUNPOD,
                "Network Performance (Gbps)": STATIC_NETWORK_PERFORMANCE_RUNPOD,
                "Commitment Discount - 1 Month Price ($/hr per GPU)": one_month_discount_hourly,
                "Commitment Discount - 3 Month Price ($/hr per GPU)": three_month_discount_hourly,
                "Commitment Discount - 6 Month Price ($/hr per GPU)": six_month_discount_hourly,
                "Commitment Discount - 12 Month Price ($/hr per GPU)": twelve_month_discount_hourly,
                "Notes / Features": f"Variant: {canonical_variant_name}. System RAM: {specs['ram']}GB. vCPUs: {specs['vcpu']}."
            }

            # --- Generate rows for different chip counts and periods ---
            # The old script generated rows for 1, 2, 4, 8 chips. We continue this for on-demand.
            for num_chips_to_calc in [1, 2, 4, 8]:
                # --- Per Hour ---
                total_hourly_price_numeric = base_1x_hourly_price * num_chips_to_calc
                row_hourly_data = {
                    **base_info_for_row,
                    "Number of Chips": num_chips_to_calc,
                    "Period": "Per Hour",
                    "Total Price ($)": round(total_hourly_price_numeric, 4),
                    "Effective Hourly Rate ($/hr)": round(base_1x_hourly_price, 4)
                }
                final_sheet_rows_unpivoted.append(row_hourly_data)
        
        except Exception as e:
            print(f"ERROR (RunPod): Failed to process a row. DisplayName: {display_name_from_runpod}. Error: {e}")
            import traceback
            traceback.print_exc()

    if final_sheet_rows_unpivoted:
        num_base_offerings = len(set(row["GPU ID"] for row in final_sheet_rows_unpivoted))
        print(f"RunPod: Processed and unpivoted data for {num_base_offerings} base GPU offerings, generating {len(final_sheet_rows_unpivoted)} total rows.")
    else:
        print("RunPod: No target GPU offerings (H100, H200, L40S) found in the new HTML.")
        
    return final_sheet_rows_unpivoted

def create_timestamped_filename(url):
    base_name = url.replace("https://", "").replace("http://", "").replace("www.", "").replace("/", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base_name}_{timestamp}.png"

def process_data_and_screenshot(driver, output_directory):
    filepath = None
    scraped_data_list = []

    try:
        print(f"Navigating to RunPod: {RUNPOD_PRICING_URL}")
        driver.get(RUNPOD_PRICING_URL)
        time.sleep(5) # ページ読み込み待機

        # フルページのスクリーンショットを撮影
        print("Taking full-page screenshot of RunPod...")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        driver.set_window_size(1920, total_height)
        time.sleep(2)

        filename = create_timestamped_filename(RUNPOD_PRICING_URL)
        filepath = f"{output_directory}/{filename}"
        
        driver.save_screenshot(filepath)
        print(f"Successfully saved RunPod screenshot to: {filepath}")

        # --- 2. 価格テキストの取得 ---
        print("Scraping pricing data from the same page...")
        # 今見ているページのHTMLを取得
        html_source = driver.page_source
        soup = BeautifulSoup(html_source, "html.parser")
        
        scraped_data_list = fetch_runpod_data(soup)
        
        return [filepath] if filepath else [], scraped_data_list # 成功した場合はファイルパスを返す

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        return [], []