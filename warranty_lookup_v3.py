#!/usr/bin/env python3
"""
American Standard Warranty Lookup - FIXED VERSION
Two-step process:
1. Enter serial → Click Search → Wait for validation
2. Click "Print my warranty" → New tab opens with PDF
"""

import asyncio
import os
from playwright.async_api import async_playwright

async def lookup_warranty(serial_number: str, headless: bool = False):
    """
    Lookup warranty with correct two-step flow.
    """
    
    output_dir = "./warranty_output"
    os.makedirs(output_dir, exist_ok=True)
    
    result = {
        "lookup_status": "pending",
        "serial_number": serial_number,
        "warranty_data": None,
        "pdf_path": None,
        "screenshot_path": None,
        "error": None
    }
    
    print(f"\n{'='*60}")
    print(f"  WARRANTY LOOKUP: {serial_number}")
    print(f"{'='*60}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=300 if not headless else 0
        )
        
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()
        
        try:
            # =================================================================
            # STEP 1: Load page
            # =================================================================
            print("[1] Loading page...")
            await page.goto(
                "https://www.americanstandardair.com/resources/warranty-and-registration/lookup/",
                wait_until="domcontentloaded",
                timeout=30000
            )
            await asyncio.sleep(2)
            print("    ✓ Page loaded")
            
            # =================================================================
            # STEP 2: Handle modal if present
            # =================================================================
            print("[2] Checking for modal...")
            
            # Look for common modal dismiss buttons
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
            
            # =================================================================
            # STEP 3: Enter serial number
            # =================================================================
            print(f"[3] Entering serial number: {serial_number}")
            
            # Try multiple selectors for serial input
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
            print("    ✓ Serial entered")
            
            # =================================================================
            # STEP 4: Click Search/Submit button (first button)
            # =================================================================
            print("[4] Clicking Search button...")
            
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
                print("    ✓ Search clicked")
            else:
                raise Exception("Could not find Search button")
            
            # =================================================================
            # STEP 5: Wait for results / "Print my warranty" button to appear
            # =================================================================
            print("[5] Waiting for results...")
            await asyncio.sleep(3)  # Give time for AJAX response
            
            # Take screenshot of current state
            await page.screenshot(path=f"{output_dir}/after_search.png")
            
            # =================================================================
            # STEP 6: Click "Print my warranty" button (opens new tab)
            # =================================================================
            print("[6] Looking for 'Print my warranty' button...")
            
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
                    if await btn.is_visible(timeout=2000):
                        print_btn = btn
                        btn_text = await btn.inner_text()
                        print(f"    ✓ Found: '{btn_text.strip()}'")
                        break
                except:
                    continue
            
            if not print_btn:
                # Maybe results are already showing? Check for warranty text
                page_text = await page.inner_text("body")
                if "Term End Date" in page_text or "Warranty" in page_text:
                    print("    → Results appear to be on page (no separate print button)")
                    await page.screenshot(path=f"{output_dir}/warranty_result.png", full_page=True)
                    result["screenshot_path"] = f"{output_dir}/warranty_result.png"
                    result["lookup_status"] = "success"
                    result["warranty_data"] = parse_warranty_text(page_text)
                    await browser.close()
                    return result
                else:
                    # List all visible buttons for debugging
                    print("\n    Available buttons on page:")
                    buttons = await page.locator("button").all()
                    for i, btn in enumerate(buttons):
                        try:
                            text = await btn.inner_text()
                            visible = await btn.is_visible()
                            if visible and text.strip():
                                print(f"      - '{text.strip()[:40]}'")
                        except:
                            pass
                    
                    raise Exception("Could not find Print button or warranty results")
            
            # Click Print button and catch new tab
            print("[7] Clicking Print button (expecting new tab)...")
            
            async with context.expect_page(timeout=15000) as new_page_info:
                await print_btn.click()
            
            new_page = await new_page_info.value
            print(f"    ✓ New tab opened: {new_page.url}")
            
            # =================================================================
            # STEP 7: Capture warranty from new tab
            # =================================================================
            print("[8] Capturing warranty info...")
            
            await new_page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)
            
            # Screenshot
            screenshot_path = f"{output_dir}/warranty_{serial_number}.png"
            await new_page.screenshot(path=screenshot_path, full_page=True)
            result["screenshot_path"] = screenshot_path
            print(f"    ✓ Screenshot: {screenshot_path}")
            
            # Try PDF
            try:
                pdf_path = f"{output_dir}/warranty_{serial_number}.pdf"
                await new_page.pdf(path=pdf_path)
                result["pdf_path"] = pdf_path
                print(f"    ✓ PDF: {pdf_path}")
            except Exception as e:
                print(f"    → PDF save failed: {e}")
            
            # Extract text
            try:
                page_text = await new_page.inner_text("body")
                result["warranty_data"] = parse_warranty_text(page_text)
                
                # Save raw text
                with open(f"{output_dir}/warranty_text.txt", "w") as f:
                    f.write(page_text)
                print(f"    ✓ Text extracted")
            except Exception as e:
                print(f"    → Text extraction failed: {e}")
            
            result["lookup_status"] = "success"
            print("\n    ✓ WARRANTY LOOKUP COMPLETE!")
            
        except Exception as e:
            result["lookup_status"] = "error"
            result["error"] = str(e)
            print(f"\n    ✗ Error: {e}")
            await page.screenshot(path=f"{output_dir}/error.png")
        
        finally:
            if not headless:
                print("\n    Keeping browser open 5 seconds...")
                await asyncio.sleep(5)
            await browser.close()
    
    return result


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
    
    # Warranty components: "Component : Term End Date is MM/DD/YYYY (X Years)"
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


def print_results(result: dict):
    """Pretty print the results."""
    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}\n")
    
    print(f"  Status: {result['lookup_status']}")
    print(f"  Serial: {result['serial_number']}")
    
    if result.get("error"):
        print(f"  Error: {result['error']}")
    
    if result.get("warranty_data"):
        wd = result["warranty_data"]
        print(f"\n  Model: {wd.get('model_number', 'N/A')}")
        print(f"  Install Date: {wd.get('install_date', 'N/A')}")
        print(f"  Registration: {wd.get('registration_type', 'N/A')}")
        
        if wd.get("components"):
            print(f"\n  WARRANTY COVERAGE:")
            for c in wd["components"]:
                print(f"    • {c['name']}: expires {c['end_date']} ({c['term_years']} yr)")
    
    if result.get("screenshot_path"):
        print(f"\n  📸 Screenshot: {result['screenshot_path']}")
    if result.get("pdf_path"):
        print(f"  📄 PDF: {result['pdf_path']}")
    
    print()


# =================================================================
# MAIN
# =================================================================

if __name__ == "__main__":
    import sys
    
    serial = "5434REB2F"
    if len(sys.argv) > 1:
        serial = sys.argv[1]
    
    result = asyncio.run(lookup_warranty(serial, headless=False))
    print_results(result)
