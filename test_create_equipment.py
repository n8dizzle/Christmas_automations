"""
Test ServiceTitan Equipment API Integration
Tests: OAuth, Job Lookup, Equipment Creation
"""

import sys
sys.path.insert(0, '.')

from servicetitan_api import (
    get_servicetitan_token,
    get_job_details,
    get_location_details,
    get_existing_equipment,
    detect_equipment_type,
    build_equipment_payload,
    create_or_update_equipment,
    find_equipment_by_serial
)


def test_auth():
    """Test OAuth token retrieval."""
    print("\n" + "="*50)
    print("  TEST 1: OAuth Token")
    print("="*50)
    
    result = get_servicetitan_token()
    
    if result.get("success"):
        token = result["access_token"]
        print(f"  ✅ Token retrieved: {token[:30]}...")
        return token
    else:
        print(f"  ❌ Auth failed: {result.get('error')}")
        return None


def test_job_lookup(token, job_id):
    """Test job details lookup."""
    print("\n" + "="*50)
    print(f"  TEST 2: Job Lookup (ID: {job_id})")
    print("="*50)
    
    result = get_job_details(job_id, token)
    
    if result.get("success"):
        print(f"  ✅ Job found!")
        print(f"     Job Number: {result.get('job_number')}")
        print(f"     Location ID: {result.get('location_id')}")
        print(f"     Customer ID: {result.get('customer_id')}")
        return result
    else:
        print(f"  ❌ Job lookup failed: {result.get('error')}")
        return None


def test_equipment_list(token, location_id):
    """Test existing equipment list."""
    print("\n" + "="*50)
    print(f"  TEST 3: Equipment at Location {location_id}")
    print("="*50)
    
    result = get_existing_equipment(location_id, token)
    
    if result.get("success"):
        count = result.get("equipment_count", 0)
        print(f"  ✅ Found {count} equipment record(s)")
        
        for equip in result.get("equipment", [])[:5]:
            print(f"     - {equip.get('name')} (Serial: {equip.get('serialNumber', 'N/A')})")
        
        return result
    else:
        print(f"  ❌ Equipment lookup failed: {result.get('error')}")
        return None


def test_equipment_type_detection():
    """Test equipment type auto-detection."""
    print("\n" + "="*50)
    print("  TEST 4: Equipment Type Detection")
    print("="*50)
    
    test_cases = [
        ("24ACC548A003", "Carrier", "Air Conditioner"),
        ("4TTR4048A1000AA", "Trane", "Air Conditioner"),
        ("TUD2B080A9V3VB", "Trane", "Gas Furnace"),
        ("4TWR4048A1000AA", "Trane", "Heat Pump"),
        ("4TEM3F49A1000AA", "Trane", "Air Handler"),
        ("UNKNOWN123", "Some Brand", "Other"),
    ]
    
    all_passed = True
    for model, mfr, expected in test_cases:
        detected = detect_equipment_type(model, mfr)
        status = "✅" if detected == expected else "❌"
        if detected != expected:
            all_passed = False
        print(f"  {status} {model} → {detected} (expected: {expected})")
    
    return all_passed


def test_payload_builder():
    """Test equipment payload building."""
    print("\n" + "="*50)
    print("  TEST 5: Payload Builder")
    print("="*50)
    
    mock_ocr = {
        "raw_extraction": {
            "manufacturer": "Trane",
            "model_line": "XR14",
            "model_number": "4TTR4048A1000AA",
            "serial_number": "TEST123456",
            "mfr_date": "October 2020",
            "refrigerant_type": "R-410A",
            "refrigerant_charge_lbs": 7,
            "refrigerant_charge_oz": 8,
            "volts": "208/230",
            "phase": 1,
            "hz": 60,
        },
        "derived_fields": {
            "tonnage": 4.0,
            "capacity_btu": 48000
        }
    }
    
    mock_warranty = {
        "lookup_status": "success",
        "warranty_data": {
            "installation_date": "10/15/2020",
            "warranty_end": "10/15/2030",
            "components": [
                {"name": "Compressor", "term_years": 10, "end_date": "10/15/2030"},
                {"name": "Parts", "term_years": 5, "end_date": "10/15/2025"},
            ]
        }
    }
    
    payload = build_equipment_payload(mock_ocr, mock_warranty, 123456789)
    
    print(f"  ✅ Payload built:")
    for key, value in payload.items():
        if key != "memo":
            print(f"     {key}: {value}")
    print(f"     memo: {payload.get('memo', '')[:60]}...")
    
    return payload


def run_all_tests(job_id=None):
    """Run all tests."""
    print("\n" + "="*60)
    print("  SERVICETITAN API INTEGRATION TESTS")
    print("="*60)
    
    # Test 1: Auth
    token = test_auth()
    if not token:
        print("\n⛔ Cannot proceed without auth token")
        return
    
    # Test 2 & 3: Job and equipment (if job_id provided)
    if job_id:
        job_info = test_job_lookup(token, job_id)
        if job_info:
            test_equipment_list(token, job_info["location_id"])
    else:
        print("\n  ⚠️ Skipping job/equipment tests (no job_id provided)")
        print("     Run with: python3 test_create_equipment.py <JOB_ID>")
    
    # Test 4: Type detection
    test_equipment_type_detection()
    
    # Test 5: Payload builder
    test_payload_builder()
    
    print("\n" + "="*60)
    print("  TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    job_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_all_tests(job_id)
