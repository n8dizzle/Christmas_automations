#!/usr/bin/env python3
"""Test Carrier warranty lookup."""

import asyncio
import sys
sys.path.insert(0, '.')

from equipment_poc import lookup_carrier_warranty

async def test_carrier():
    # Use the placeholder serial from the Carrier form as a test
    serial = "2119Q27445"
    
    if len(sys.argv) > 1:
        serial = sys.argv[1]
    
    print(f"\nTesting Carrier warranty lookup with serial: {serial}\n")
    
    result = await lookup_carrier_warranty(serial)
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Status: {result['lookup_status']}")
    print(f"Serial: {result['serial_number']}")
    
    if result.get('error'):
        print(f"Error: {result['error']}")
    
    if result.get('warranty_data'):
        print("\nWarranty Data:")
        for key, value in result['warranty_data'].items():
            if key != 'raw_text_snippet':
                print(f"  {key}: {value}")
    
    if result.get('screenshot_path'):
        print(f"\n📸 Screenshot: {result['screenshot_path']}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_carrier())
