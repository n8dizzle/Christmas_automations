import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright
import json

# ============================================================================
# WARRANTY LOOKUP VIA BROWSER AUTOMATION
# ============================================================================

async def lookup_warranty(serial_number: str, manufacturer: str) -> dict:
    """
    Look up warranty information based on manufacturer.
    Currently supports Trane/American Standard.
    """
    # Normalize manufacturer
    mfr_lower = manufacturer.lower()
    
    if "trane" in mfr_lower or "american standard" in mfr_lower:
        return await lookup_trane_warranty(serial_number)
    elif "carrier" in mfr_lower:
        return await lookup_carrier_warranty(serial_number)
    else:
        return {
            "lookup_status": "unsupported",
            "error": f"Warranty lookup not yet implemented for {manufacturer}"
        }

async def lookup_trane_warranty(serial_number: str) -> dict:
    """
    Look up warranty information from American Standard's website using Playwright.
    Handles results that might appear in a new tab (PDF or page).
    Refactored to match warranty_lookup_v3 logic.
    """
    
    output_dir = "./warranty_output"
    os.makedirs(output_dir, exist_ok=True)
    
    warranty_info = {
        "lookup_status": "pending",
        "serial_number": serial_number,
        "warranty_data": None,
        "error": None,
        "pdf_url": None,
        "debug_screenshot": None
    }
    
    async with async_playwright() as p:
        # Headed mode required for blob URL PDF viewer
        browser = await p.chromium.launch(headless=False)
        # Enable downloads
        context = await browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 900}) 
        page = await context.new_page()
        
        try:
            # [1] Load page
            print(f"  → Navigating to American Standard warranty lookup...")
            await page.goto("https://www.americanstandardair.com/resources/warranty-and-registration/lookup/", 
                          timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # [2] Handle modal if present
            print("  → Checking for modal...")
            modal_selectors = [
                 "button:has-text('Next')",
                 "button:has-text('Continue')",
                 "button:has-text('Close')",
                 "button:has-text('I Understand')",
                 ".modal button",
                 "[class*='modal'] button:not([disabled])",
            ]
            for selector in modal_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print(f"    ✓ Dismissed modal with: {selector}")
                        await asyncio.sleep(1)
                        break
                except:
                    continue
            
            # Cookie Banner
            try:
                if await page.locator("#onetrust-accept-btn-handler").is_visible(timeout=1000):
                     await page.locator("#onetrust-accept-btn-handler").click()
            except: pass

            # [3] Enter serial number
            print(f"  → Entering serial number: {serial_number}")
            serial_input = None
            for selector in ["#serialNumber", "input[name='serialNumber']", "input[type='text']"]:
                try:
                    inp = page.locator(selector).first
                    if await inp.is_visible(timeout=1000):
                        serial_input = inp
                        break
                except:
                    continue
            
            if not serial_input:
                raise Exception("Could not find serial number input")
            
            await serial_input.clear()
            await serial_input.fill(serial_number)
            await asyncio.sleep(0.5)

            # [4] Click Search/Submit button
            print("  → Clicking Search button...")
            search_btn = None
            for selector in ["button:has-text('Search')", "button[type='submit']", "button:has-text('Look')"]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        search_btn = btn
                        break
                except:
                    continue
            
            if search_btn:
                await search_btn.click()
            else:
                # Try Enter
                await serial_input.press("Enter")
            
            # [5] Wait for results / "Print my warranty" button
            print("  → Waiting for results...")
            await asyncio.sleep(3)
            
            # [6] Click "Print my warranty" button (opens new tab)
            print("  → Looking for 'Print my warranty' button...")
            print_btn = None
            for selector in [
                "button:has-text('Print my warranty')",
                "button:has-text('Print')",
                "a:has-text('Print my warranty')",
                "button:has-text('View Warranty')",
                "[class*='print']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=3000):
                        print_btn = btn
                        break
                except:
                    continue
            
            if not print_btn:
                # Maybe results are already showing on page?
                page_text = await page.inner_text("body")
                if "Term End Date" in page_text or "Warranty" in page_text:
                     print("    → Results on page")
                     warranty_info["lookup_status"] = "success"
                     warranty_info["warranty_data"] = parse_warranty_text(page_text)
                elif await page.locator(".warranty-error").is_visible():
                     warranty_info["lookup_status"] = "not_found"
                     warranty_info["error"] = "Serial number not found"
                else:
                    raise Exception("Could not find 'Print my warranty' button or results")
            else:
                # Click Print button and catch new tab
                print("  → Clicking Print button (expecting new tab)...")
                try:
                    async with context.expect_page(timeout=15000) as new_page_info:
                        await print_btn.click()
                    
                    new_page = await new_page_info.value
                    print(f"    ✓ New tab opened: {new_page.url}")
                    
                    warranty_info["lookup_status"] = "success"
                    warranty_info["pdf_url"] = new_page.url
                    
                    await new_page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(3)  # Let PDF fully render
                    
                    # Take screenshot of the warranty document
                    screenshot_path = f"{output_dir}/warranty_{serial_number}.png"
                    try:
                        temp_path = f"{output_dir}/warranty_{serial_number}_temp.png"
                        await new_page.screenshot(path=temp_path, full_page=False, timeout=20000)
                        
                        # Crop out the PDF viewer sidebar (left ~270px)
                        from PIL import Image
                        img = Image.open(temp_path)
                        # Crop: left=270, top=0, right=width, bottom=height
                        width, height = img.size
                        cropped = img.crop((270, 0, width, height))
                        cropped.save(screenshot_path)
                        os.remove(temp_path)  # Clean up temp file
                        
                        warranty_info["screenshot_path"] = screenshot_path
                        print(f"    ✓ Screenshot saved: {screenshot_path} ({cropped.size[0]}x{cropped.size[1]})")
                    except Exception as e:
                        print(f"    Screenshot failed: {e}")
                    
                    # Extract warranty data from page text for parsing
                    try:
                        page_text = await new_page.inner_text("body", timeout=5000)
                        warranty_info["warranty_data"] = parse_warranty_text(page_text)
                        if warranty_info["warranty_data"].get("components"):
                            print(f"    ✓ Parsed warranty data")
                    except Exception as e:
                        print(f"    Text extraction failed: {e}")
                        if not warranty_info.get("warranty_data"):
                            warranty_info["warranty_data"] = {"source": "Screenshot saved", "note": "Text extraction failed"}

                except Exception as e:
                    print(f"New tab handling failed: {e}")
                    # If we got the URL, it's still a partial success
                    if warranty_info.get("pdf_url"):
                         warranty_info["lookup_status"] = "success"
                         warranty_info["error"] = f"Document opened but processing failed: {e}"
                    else:
                        warranty_info["lookup_status"] = "success_no_data" 
                        warranty_info["error"] = f"Warranty found but could not parse new tab: {e}"

        except Exception as e:
            warranty_info["lookup_status"] = "error"
            warranty_info["error"] = str(e)
            try:
                await page.screenshot(path="debug_error.png")
                warranty_info["debug_screenshot"] = "debug_error.png"
            except: pass
            
        finally:
            await browser.close()
    
    return warranty_info


async def lookup_carrier_warranty(serial_number: str) -> dict:
    """
    Look up warranty information from Carrier's website using Playwright.
    
    Flow:
    1. Navigate to Carrier warranty lookup page
    2. Enter serial number
    3. Select "Yes" for original purchaser
    4. Click Submit
    5. Capture results from same page
    """
    
    output_dir = "./warranty_output"
    os.makedirs(output_dir, exist_ok=True)
    
    warranty_info = {
        "lookup_status": "pending",
        "serial_number": serial_number,
        "manufacturer": "Carrier",
        "warranty_data": None,
        "error": None,
        "screenshot_path": None,
        "debug_screenshot": None
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        
        try:
            # [1] Load page
            print(f"  → Navigating to Carrier warranty lookup...")
            await page.goto(
                "https://www.carrier.com/residential/en/us/warranty-lookup/",
                timeout=30000,
                wait_until="domcontentloaded"
            )
            await asyncio.sleep(2)
            
            # [2] Handle cookie consent banner if present
            print("  → Checking for cookie banner...")
            cookie_selectors = [
                "#onetrust-accept-btn-handler",
                "button:has-text('Accept')",
                "button:has-text('Accept All')",
                "[class*='cookie'] button",
            ]
            for selector in cookie_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print(f"    ✓ Dismissed cookie banner: {selector}")
                        await asyncio.sleep(0.5)
                        break
                except:
                    continue
            
            # [3] Enter serial number
            print(f"  → Entering serial number: {serial_number}")
            serial_input = page.locator("#serialNumber")
            
            if not await serial_input.is_visible(timeout=5000):
                raise Exception("Could not find serial number input (#serialNumber)")
            
            await serial_input.clear()
            await serial_input.fill(serial_number)
            await asyncio.sleep(0.5)
            print("    ✓ Serial number entered")
            
            # [4] Select "Yes" for original purchaser
            print("  → Selecting 'Yes' for original purchaser...")
            original_yes = page.locator("#isOriginal1")
            
            if await original_yes.is_visible(timeout=2000):
                await original_yes.click()
                print("    ✓ Selected 'Yes'")
            else:
                # Try clicking the label instead
                label = page.locator("label[for='isOriginal1']")
                if await label.is_visible(timeout=1000):
                    await label.click()
                    print("    ✓ Selected 'Yes' via label")
                else:
                    print("    ⚠ Could not find original purchaser radio, continuing anyway")
            
            await asyncio.sleep(0.5)
            
            # [5] Click Submit button
            print("  → Clicking Submit button...")
            submit_btn = page.locator("#btnSubmit")
            
            if not await submit_btn.is_visible(timeout=2000):
                # Try alternative selectors
                for selector in ["input[type='submit']", "button:has-text('Submit')"]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1000):
                            submit_btn = btn
                            break
                    except:
                        continue
            
            await submit_btn.click()
            print("    ✓ Submit clicked")
            
            # [6] Wait for results
            print("  → Waiting for warranty results...")
            await asyncio.sleep(4)  # Give time for AJAX response
            
            # Take screenshot of results
            screenshot_path = f"{output_dir}/warranty_carrier_{serial_number}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            warranty_info["screenshot_path"] = screenshot_path
            print(f"    ✓ Screenshot saved: {screenshot_path}")
            
            # [7] Extract warranty data from page
            page_text = await page.inner_text("body")
            
            # Check for error messages
            if "not found" in page_text.lower() or "no warranty" in page_text.lower():
                warranty_info["lookup_status"] = "not_found"
                warranty_info["error"] = "Serial number not found or no warranty on file"
            elif "error" in page_text.lower() and "please try again" in page_text.lower():
                warranty_info["lookup_status"] = "error"
                warranty_info["error"] = "Website returned an error"
            else:
                # Parse the warranty data
                warranty_info["lookup_status"] = "success"
                warranty_info["warranty_data"] = parse_carrier_warranty_text(page_text)
                print("    ✓ Warranty data extracted")
                
                # Save raw text for debugging
                with open(f"{output_dir}/carrier_raw_text.txt", "w") as f:
                    f.write(page_text)
            
        except Exception as e:
            warranty_info["lookup_status"] = "error"
            warranty_info["error"] = str(e)
            print(f"    ✗ Error: {e}")
            try:
                await page.screenshot(path=f"{output_dir}/carrier_error.png")
                warranty_info["debug_screenshot"] = f"{output_dir}/carrier_error.png"
            except:
                pass
        
        finally:
            await browser.close()
    
    return warranty_info


def parse_carrier_warranty_text(text: str) -> dict:
    """
    Parse warranty info from Carrier warranty page text.
    Extracts all fields needed for ServiceTitan equipment records.
    """
    import re
    from datetime import datetime
    
    warranty = {
        # Core equipment info
        "model_number": None,
        "serial_number": None,
        "brand": None,
        "manufacturer": "Carrier",  # Parent company
        "product_type": None,
        
        # Dates
        "installation_date": None,
        "warranty_start": None,
        "warranty_end": None,
        
        # Derived fields
        "tonnage": None,
        "capacity": None,
        "age_years": None,
        
        # Warranty components (Coil, Compressor, etc.)
        "components": [],
        
        # Status
        "warranty_status": None,
        
        # For debugging
        "raw_text_snippet": None
    }
    
    # =========================================================================
    # Extract Model Number
    # =========================================================================
    # Carrier format example: N5A5S48AKAWA
    model_patterns = [
        r'Model\s*#?\s*:?\s*([A-Z0-9]{8,})',
        r'Model Number\s*:?\s*([A-Z0-9]{8,})',
    ]
    for pattern in model_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            warranty["model_number"] = match.group(1).strip()
            break
    
    # =========================================================================
    # Extract Serial Number
    # =========================================================================
    serial_patterns = [
        r'Serial\s*#?\s*:?\s*([A-Z0-9]{8,})',
        r'Serial Number\s*:?\s*([A-Z0-9]{8,})',
    ]
    for pattern in serial_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            warranty["serial_number"] = match.group(1).strip()
            break
    
    # =========================================================================
    # Detect Brand (Carrier family brands)
    # =========================================================================
    brand_keywords = {
        "comfortmaker": "Comfortmaker",
        "carrier": "Carrier", 
        "bryant": "Bryant",
        "payne": "Payne",
        "heil": "Heil",
        "tempstar": "Tempstar",
        "day & night": "Day & Night",
        "arcoaire": "Arcoaire",
        "keeprite": "Keeprite",
    }
    text_lower = text.lower()
    for keyword, brand_name in brand_keywords.items():
        if keyword in text_lower:
            warranty["brand"] = brand_name
            break
    
    # If no brand found, default based on model prefix
    if not warranty["brand"] and warranty["model_number"]:
        model = warranty["model_number"].upper()
        # Carrier brand prefixes
        if model.startswith("24"):
            warranty["brand"] = "Carrier"
        elif model.startswith("N5"):
            warranty["brand"] = "Comfortmaker"
    
    # =========================================================================
    # Extract Warranty Components (Coil, Compressor, etc.)
    # Actual format from Carrier: "Coil help_outline\t10 years\t08/07/2035"
    # =========================================================================
    component_pattern = r'(Coil|Coil TIN|Compressor|Enhanced Parts Warranty|Parts|Labor|Heat Exchanger|Functional Parts)\s*(?:help_outline)?\s+(\d+)\s*years?\s+(\d{1,2}/\d{1,2}/\d{4})'
    matches = re.findall(component_pattern, text, re.IGNORECASE)
    
    warranty_end_date = None
    warranty_years = None
    
    for component_name, years, end_date in matches:
        component = {
            "name": component_name.strip(),
            "term_years": int(years),
            "end_date": end_date.strip()
        }
        warranty["components"].append(component)
        
        # Track the longest warranty for main warranty end date
        if warranty_end_date is None or int(years) > warranty_years:
            warranty_end_date = end_date.strip()
            warranty_years = int(years)
    
    # =========================================================================
    # Calculate Installation Date from Warranty End Date
    # =========================================================================
    if warranty_end_date and warranty_years:
        try:
            end_dt = datetime.strptime(warranty_end_date, "%m/%d/%Y")
            install_dt = end_dt.replace(year=end_dt.year - warranty_years)
            warranty["installation_date"] = install_dt.strftime("%m/%d/%Y")
            warranty["warranty_start"] = warranty["installation_date"]
            warranty["warranty_end"] = warranty_end_date
            
            # Calculate age
            today = datetime.now()
            age_delta = today - install_dt
            warranty["age_years"] = round(age_delta.days / 365.25, 1)
        except:
            pass
    
    # =========================================================================
    # Derive Tonnage from Model Number
    # Carrier model numbers typically encode tonnage: e.g., N5A5S48AKAWA
    # The "48" indicates 48,000 BTU = 4 tons (12,000 BTU per ton)
    # =========================================================================
    if warranty["model_number"]:
        model = warranty["model_number"].upper()
        # Look for 2-3 digit number that represents BTU in thousands
        btu_match = re.search(r'[A-Z](\d{2,3})[A-Z]', model)
        if btu_match:
            btu_thousands = int(btu_match.group(1))
            # Common BTU values: 18, 24, 30, 36, 42, 48, 60 (1.5 to 5 tons)
            if 12 <= btu_thousands <= 72:
                tonnage = btu_thousands / 12
                warranty["tonnage"] = tonnage
                warranty["capacity"] = f"{tonnage} tons"
    
    # =========================================================================
    # Determine Product Type from Model Number
    # =========================================================================
    if warranty["model_number"]:
        model = warranty["model_number"].upper()
        # Common prefixes/patterns
        if "A" in model[:3] or "AC" in model[:4]:
            warranty["product_type"] = "A/C Condenser"
        elif "G" in model[:2] or "GAS" in model.upper():
            warranty["product_type"] = "Gas Furnace"
        elif "H" in model[:2] and "P" in model[:4]:
            warranty["product_type"] = "Heat Pump"
        elif "AH" in model[:4] or "FAN" in model.upper():
            warranty["product_type"] = "Air Handler"
        elif "COIL" in model.upper():
            warranty["product_type"] = "Evaporator Coil"
    
    # =========================================================================
    # Check Warranty Status
    # =========================================================================
    if warranty.get("warranty_end"):
        try:
            end_dt = datetime.strptime(warranty["warranty_end"], "%m/%d/%Y")
            if end_dt > datetime.now():
                warranty["warranty_status"] = "Active"
            else:
                warranty["warranty_status"] = "Expired"
        except:
            pass
    
    if not warranty["warranty_status"]:
        if "active" in text_lower or "valid" in text_lower:
            warranty["warranty_status"] = "Active"
        elif "expired" in text_lower:
            warranty["warranty_status"] = "Expired"
    
    # =========================================================================
    # Save raw text snippet for debugging
    # =========================================================================
    warranty_section = text[:800] if len(text) > 800 else text
    warranty["raw_text_snippet"] = warranty_section.replace("\n", " ").strip()
    
    return warranty


def parse_warranty_text(text: str) -> dict:
    """Parse warranty info from page text."""
    import re
    
    warranty = {
        "model_number": None,
        "serial_number": None,
        "registration_type": None,
        "install_date": None,
        "components": []
    }
    
    # Model/Serial
    model_match = re.search(r'Model#?\s*([A-Z0-9]+)', text)
    if model_match:
        warranty["model_number"] = model_match.group(1)
    
    serial_match = re.search(r'Serial#?\s*([A-Z0-9]+)', text)
    if serial_match:
        warranty["serial_number"] = serial_match.group(1)
    
    # Registration type
    if "Residential Base" in text:
        warranty["registration_type"] = "Residential Base"
    elif "Residential Extended" in text:
        warranty["registration_type"] = "Residential Extended"
    
    # Warranty components
    pattern = r'([A-Za-z\s]+?)\s*:\s*Term End Date is\s*(\d{2}/\d{2}/\d{4})\s*\((\d+)\s*Years?\)'
    matches = re.findall(pattern, text)
    
    for component_name, end_date, years in matches:
        warranty["components"].append({
            "name": component_name.strip(),
            "end_date": end_date,
            "term_years": int(years)
        })
        
        # Calculate install date from first component
        if warranty["install_date"] is None:
            try:
                from datetime import datetime
                end = datetime.strptime(end_date, "%m/%d/%Y")
                install = end.replace(year=end.year - int(years))
                warranty["install_date"] = install.strftime("%m/%d/%Y")
            except:
                pass
    
    return warranty


# ============================================================================
# FORMAT FOR SERVICETITAN
# ============================================================================

def format_for_servicetitan(extracted_data: dict, warranty_info: dict) -> dict:
    """
    Format the extracted data into ServiceTitan's installed-equipment API format.
    """
    
    # Handle cases where extracted_data might be flat or nested
    if "raw_extraction" in extracted_data:
        raw = extracted_data["raw_extraction"]
        derived = extracted_data.get("derived_fields", {})
    else:
        # Assuming flat structure from Gemini
        raw = extracted_data
        derived = extracted_data  # Or calculate derived here
    
    # Build the memo field with useful info
    memo_parts = [
        f"OCR Processed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Model Line: {raw.get('model_line', 'N/A')}",
        f"Refrigerant: {raw.get('refrigerant_type', 'N/A')}",
    ]
    
    if derived.get('tonnage'):
         memo_parts.append(f"Tonnage: {derived.get('tonnage')} tons")
    
    # Parse warranty dates if available
    warranty_start = None
    warranty_end = None
    
    if warranty_info.get("warranty_data"):
        wd = warranty_info["warranty_data"]
        # Try to extract dates from warranty data
        if "installation_date" in wd:
            warranty_start = wd["installation_date"]
        if "warranty_expiration" in wd:
            warranty_end = wd["warranty_expiration"]
    
    # If no warranty info, use manufacture date as install date estimate
    if not warranty_start and raw.get("mfr_date"):
        # Very rough fallback
        warranty_start = raw.get("mfr_date")
    
    servicetitan_format = {
        # Required fields (locationId and customerId would come from the job)
        "locationId": "<<REQUIRED: From Job>>",
        "customerId": "<<REQUIRED: From Job>>",
        
        # Equipment identification
        "name": f"{raw.get('manufacturer', '')} {raw.get('model_line', '')}",
        "manufacturer": raw.get("manufacturer", ""),
        "model": raw.get("model_number", ""),
        "serialNumber": raw.get("serial_number", ""),
        
        # Dates
        "installedOn": warranty_start,
        "manufacturerWarrantyStart": warranty_start,
        "manufacturerWarrantyEnd": warranty_end,
        
        # Additional info
        "memo": " | ".join(memo_parts),
        "status": "Installed",
    }
    
    return servicetitan_format

# ============================================================================
# GENERATE REPORT
# ============================================================================

def generate_report(extracted_data: dict, warranty_info: dict, servicetitan_format: dict) -> str:
    """
    Generate a clean, formatted report of all the data.
    """
    
    if "raw_extraction" in extracted_data:
        raw = extracted_data["raw_extraction"]
        derived = extracted_data.get("derived_fields", {})
    else:
        raw = extracted_data
        derived = extracted_data
    
    report = []
    report.append("=" * 70)
    report.append("  EQUIPMENT DATA EXTRACTION & WARRANTY LOOKUP REPORT")
    report.append("  Christmas Air Conditioning and Plumbing")
    report.append("=" * 70)
    report.append("")
    
    # Classification
    report.append("┌─ IMAGE CLASSIFICATION ─────────────────────────────────────────────┐")
    report.append(f"│  Is Data Plate:  ✅ YES                                            │")
    if 'confidence' in extracted_data:
        report.append(f"│  Confidence:     {extracted_data['confidence']*100:.0f}%                                             │")
    report.append("└────────────────────────────────────────────────────────────────────┘")
    report.append("")
    
    # Equipment Details
    report.append("┌─ EQUIPMENT DETAILS ────────────────────────────────────────────────┐")
    report.append(f"│  Manufacturer:   {raw.get('manufacturer', 'N/A'):<50} │")
    report.append(f"│  Model Line:     {raw.get('model_line', 'N/A'):<50} │")
    report.append(f"│  Model Number:   {raw.get('model_number', 'N/A'):<50} │")
    report.append(f"│  Serial Number:  {raw.get('serial_number', 'N/A'):<50} │")
    report.append(f"│  MFR Date:       {raw.get('mfr_date', 'N/A'):<50} │")
    report.append(f"│  Age:            {derived.get('age_years', 'N/A')} years                                          │")
    report.append("└────────────────────────────────────────────────────────────────────┘")
    report.append("")
    
    # Warranty Status
    report.append("┌─ WARRANTY LOOKUP ──────────────────────────────────────────────────┐")
    status = warranty_info.get("lookup_status", "unknown")
    if status == "success":
        report.append(f"│  Status:         ✅ WARRANTY INFO FOUND                           │")
        wd = warranty_info.get("warranty_data", {})
        for key, value in wd.items():
            display_key = key.replace("_", " ").title()[:20]
            display_val = str(value)[:45]
            report.append(f"│  {display_key:<18} {display_val:<47} │")
    elif status == "not_found":
        report.append(f"│  Status:         ⚠️  NOT REGISTERED                               │")
    else:
        report.append(f"│  Status:         ❌ LOOKUP FAILED                                 │")
    report.append("└────────────────────────────────────────────────────────────────────┘")
    report.append("")
    
    return "\n".join(report)


# ============================================================================
# SERVICETITAN ATTACHMENT UPLOAD
# ============================================================================

async def upload_warranty_to_servicetitan(
    job_id: int,
    file_path: str,
    tenant_id: str,
    access_token: str,
    file_name: str = None,
    attachment_type: str = "Other",
    app_key: str = None
) -> dict:
    """
    Upload a warranty PDF/image as an attachment to a ServiceTitan job.
    """
    import aiohttp
    import base64
    
    result = {
        "upload_status": "pending",
        "job_id": job_id,
        "file_path": file_path,
        "response": None,
        "error": None
    }
    
    # Validate file exists
    if not os.path.exists(file_path):
        result["upload_status"] = "error"
        result["error"] = f"File not found: {file_path}"
        return result
    
    # Determine file name
    if file_name is None:
        file_name = os.path.basename(file_path)
    
    # Read file and encode as base64
    try:
        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        result["upload_status"] = "error"
        result["error"] = f"Failed to read file: {e}"
        return result
    
    # ServiceTitan API endpoint (Forms API for attachments)
    url = f"https://api.servicetitan.io/forms/v2/tenant/{tenant_id}/jobs/{job_id}/attachments"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        # Don't set Content-Type - aiohttp will set it for FormData
    }
    
    if app_key:
        headers["ST-App-Key"] = app_key
    
    try:
        # Read file as binary
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        # Use FormData for multipart upload
        from aiohttp import FormData
        
        data = FormData()
        data.add_field('file', file_bytes, 
                       filename=file_name,
                       content_type='image/png' if file_path.endswith('.png') else 'application/pdf')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                response_text = await response.text()
                
                if response.status in [200, 201]:
                    result["upload_status"] = "success"
                    try:
                        result["response"] = json.loads(response_text)
                    except:
                        result["response"] = response_text
                    print(f"  ✓ Uploaded {file_name} to Job {job_id}")
                else:
                    result["upload_status"] = "error"
                    result["error"] = f"API returned {response.status}: {response_text}"
                    print(f"  ✗ Upload failed: {response.status}")
    
    except Exception as e:
        result["upload_status"] = "error"
        result["error"] = str(e)
    
    return result


async def upload_warranty_to_equipment(
    equipment_id: int,
    file_path: str,
    tenant_id: str,
    access_token: str,
    file_name: str = None,
    app_key: str = None
) -> dict:
    """
    Upload a warranty PDF as an attachment to a ServiceTitan Equipment record.
    
    Args:
        equipment_id: The ServiceTitan installed equipment ID
        file_path: Local path to the PDF or image file
        tenant_id: ServiceTitan tenant ID
        access_token: OAuth2 access token
        file_name: Optional display name for the file
        app_key: ServiceTitan app key
    
    Returns:
        dict with upload status and response data
    """
    import aiohttp
    
    result = {
        "upload_status": "pending",
        "equipment_id": equipment_id,
        "file_path": file_path,
        "response": None,
        "error": None
    }
    
    # Validate file exists
    if not os.path.exists(file_path):
        result["upload_status"] = "error"
        result["error"] = f"File not found: {file_path}"
        return result
    
    # Determine file name
    if file_name is None:
        file_name = os.path.basename(file_path)
    
    # Determine content type
    ext = os.path.splitext(file_path)[1].lower()
    content_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg"
    }
    content_type = content_types.get(ext, "application/octet-stream")
    
    # ServiceTitan API endpoint (Equipment Systems API)
    url = f"https://api.servicetitan.io/equipmentsystems/v2/tenant/{tenant_id}/installed-equipment/attachments"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    
    if app_key:
        headers["ST-App-Key"] = app_key
    
    try:
        # Read file as binary
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        # Use FormData for multipart upload
        from aiohttp import FormData
        
        data = FormData()
        data.add_field('file', file_bytes, filename=file_name, content_type=content_type)
        data.add_field('installedEquipmentId', str(equipment_id))
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                response_text = await response.text()
                
                if response.status in [200, 201]:
                    result["upload_status"] = "success"
                    try:
                        result["response"] = json.loads(response_text)
                    except:
                        result["response"] = response_text
                    print(f"  ✓ Uploaded {file_name} to Equipment {equipment_id}")
                else:
                    result["upload_status"] = "error"
                    result["error"] = f"API returned {response.status}: {response_text}"
                    print(f"  ✗ Upload failed: {response.status}")
    
    except Exception as e:
        result["upload_status"] = "error"
        result["error"] = str(e)
    
    return result
