"""
ServiceTitan API Integration Module
Handles OAuth authentication, job/location lookup, and equipment CRUD operations.
"""

import requests
import aiohttp
import os
import json
from datetime import datetime
from servicetitan_config import TENANT_ID, CLIENT_ID, CLIENT_SECRET, APP_KEY, API_BASE, AUTH_URL


# ============================================================================
# EQUIPMENT TYPE DETECTION & MAPPING
# ============================================================================

EQUIPMENT_TYPES = {
    "Air Conditioner": {
        "patterns": ["AC", "A/C", "condenser", "split", "24AC", "24ACC", "4AC", "4ACC", "2TTR", "4TTR", "XR1"],
        "model_prefixes": ["24", "4A"],
    },
    "Gas Furnace": {
        "patterns": ["furnace", "GAS", "80%", "95%", "96%", "TUD", "TDD", "XC95", "S9V2", "S8X"],
        "model_prefixes": ["58", "59"],
    },
    "Heat Pump": {
        "patterns": ["HP", "heat pump", "4TWR", "4TWX", "XL16", "XL15", "XL20i", "25HP"],
        "model_prefixes": ["25"],
    },
    "Air Handler": {
        "patterns": ["AH", "air handler", "fan coil", "4TEE", "4TEM", "TWE", "GAM"],
        "model_prefixes": [],
    },
    "Package Unit": {
        "patterns": ["package", "packaged", "rooftop", "RTU", "4YCC", "4YCY", "48TM"],
        "model_prefixes": ["48"],
    },
    "Evaporator Coil": {
        "patterns": ["coil", "evap", "4PXC", "4TXC", "CNPV"],
        "model_prefixes": [],
    },
    "Mini Split": {
        "patterns": ["mini", "ductless", "4MXW", "4MXX", "4MYW"],
        "model_prefixes": [],
    },
}


def detect_equipment_type(model_number: str, manufacturer: str = None, product_type_hint: str = None) -> str:
    """
    Auto-detect equipment type from model number patterns.
    Returns the best-guess equipment type string.
    """
    if not model_number:
        return product_type_hint if product_type_hint else "Other"
    
    model_upper = str(model_number).upper()
    
    # Check for pattern matches
    for equip_type, config in EQUIPMENT_TYPES.items():
        # Check patterns
        for pattern in config["patterns"]:
            if pattern.upper() in model_upper:
                return equip_type
        
        # Check model prefixes
        for prefix in config["model_prefixes"]:
            if model_upper.startswith(prefix):
                return equip_type
    
    # Use product_type_hint if provided and no match found
    if product_type_hint:
        return product_type_hint
    
    return "Other"


def get_all_equipment_types() -> list:
    """Return list of all available equipment types for dropdown."""
    return list(EQUIPMENT_TYPES.keys()) + ["Other", "Water Heater", "Boiler", "Thermostat"]


# ============================================================================
# SERVICETITAN API - AUTHENTICATION
# ============================================================================

_token_cache = {
    "token": None,
    "expires_at": None
}


def get_servicetitan_token(force_refresh: bool = False) -> dict:
    """
    Get OAuth2 access token from ServiceTitan.
    Caches token until near expiration.
    Returns dict with 'access_token' or 'error'.
    """
    # Check cache
    if not force_refresh and _token_cache["token"] and _token_cache["expires_at"]:
        if datetime.now().timestamp() < _token_cache["expires_at"] - 60:  # 1 min buffer
            return {
                "success": True,
                "access_token": _token_cache["token"],
                "cached": True
            }
    
    try:
        response = requests.post(
            AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            
            # Cache the token
            _token_cache["token"] = token
            _token_cache["expires_at"] = datetime.now().timestamp() + expires_in
            
            return {
                "success": True,
                "access_token": token,
                "expires_in": expires_in,
                "cached": False
            }
        else:
            return {
                "success": False,
                "error": f"Auth failed: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Auth exception: {str(e)}"
        }


# ============================================================================
# SERVICETITAN API - JOB & LOCATION LOOKUP
# ============================================================================

def get_job_details(job_id: int, access_token: str) -> dict:
    """
    Fetch job details from ServiceTitan to get locationId and customerId.
    """
    url = f"{API_BASE}/jpm/v2/tenant/{TENANT_ID}/jobs/{job_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "job_id": job_id,
                "location_id": data.get("locationId"),
                "customer_id": data.get("customerId"),
                "job_number": data.get("jobNumber"),
                "job_status": data.get("jobStatus"),
                "business_unit": data.get("businessUnitId"),
                "summary": data.get("summary", ""),
                "raw_data": data
            }
        elif response.status_code == 404:
            return {
                "success": False,
                "error": f"Job {job_id} not found"
            }
        else:
            return {
                "success": False,
                "error": f"API error: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def get_location_details(location_id: int, access_token: str) -> dict:
    """
    Fetch location details from ServiceTitan.
    """
    url = f"{API_BASE}/crm/v2/tenant/{TENANT_ID}/locations/{location_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            return {
                "success": True,
                "location_id": location_id,
                "customer_id": data.get("customerId"),
                "name": data.get("name", ""),
                "address": f"{address.get('street', '')} {address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}",
                "raw_data": data
            }
        else:
            return {
                "success": False,
                "error": f"Location lookup failed: {response.status_code}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def get_customer_details(customer_id: int, access_token: str) -> dict:
    """
    Fetch customer details from ServiceTitan.
    """
    url = f"{API_BASE}/crm/v2/tenant/{TENANT_ID}/customers/{customer_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "customer_id": customer_id,
                "name": data.get("name", ""),
                "type": data.get("type", ""),
                "raw_data": data
            }
        else:
            return {
                "success": False,
                "error": f"Customer lookup failed: {response.status_code}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def get_existing_equipment(location_id: int, access_token: str) -> dict:
    """
    Fetch existing equipment at a location for update/duplicate detection.
    """
    url = f"{API_BASE}/equipmentsystems/v2/tenant/{TENANT_ID}/installed-equipment"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    params = {
        "locationId": location_id,
        "pageSize": 100
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            equipment_list = data.get("data", [])
            return {
                "success": True,
                "location_id": location_id,
                "equipment_count": len(equipment_list),
                "equipment": equipment_list
            }
        else:
            return {
                "success": False,
                "error": f"Equipment lookup failed: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


# ============================================================================
# SERVICETITAN API - EQUIPMENT CREATION & UPDATE
# ============================================================================

def create_equipment_record(equipment_data: dict, access_token: str) -> dict:
    """
    Create a new equipment record in ServiceTitan.
    
    Required fields in equipment_data:
    - locationId (int)
    
    Optional fields:
    - name, manufacturer, model, serialNumber, installedOn
    - manufacturerWarrantyStart, manufacturerWarrantyEnd
    - serviceProviderWarrantyStart, serviceProviderWarrantyEnd
    - type, capacity, status, memo
    """
    url = f"{API_BASE}/equipmentsystems/v2/tenant/{TENANT_ID}/installed-equipment"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json=equipment_data, timeout=30)
        
        if response.status_code in [200, 201]:
            data = response.json()
            return {
                "success": True,
                "equipment_id": data.get("id"),
                "message": "Equipment record created successfully",
                "data": data
            }
        else:
            return {
                "success": False,
                "error": f"Create failed: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def update_equipment_record(equipment_id: int, equipment_data: dict, access_token: str) -> dict:
    """
    Update an existing equipment record in ServiceTitan.
    """
    url = f"{API_BASE}/equipmentsystems/v2/tenant/{TENANT_ID}/installed-equipment/{equipment_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.patch(url, headers=headers, json=equipment_data, timeout=30)
        
        if response.status_code in [200, 204]:
            return {
                "success": True,
                "equipment_id": equipment_id,
                "message": "Equipment record updated successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Update failed: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def find_equipment_by_serial(serial_number: str, location_id: int, access_token: str) -> dict:
    """
    Search for existing equipment by serial number at a location.
    Returns the equipment if found, None otherwise.
    """
    existing = get_existing_equipment(location_id, access_token)
    
    if not existing.get("success"):
        return existing
    
    for equip in existing.get("equipment", []):
        if serial_number and equip.get("serialNumber", "").upper() == serial_number.upper():
            return {
                "success": True,
                "found": True,
                "equipment_id": equip.get("id"),
                "equipment": equip
            }
    
    return {
        "success": True,
        "found": False,
        "equipment": None
    }


def create_or_update_equipment(equipment_data: dict, access_token: str) -> dict:
    """
    Smart create/update: If equipment with same serial exists at location, update it.
    Otherwise, create new.
    """
    serial = equipment_data.get("serialNumber", "")
    location_id = equipment_data.get("locationId")
    
    if serial and location_id:
        # Check for existing
        existing = find_equipment_by_serial(serial, location_id, access_token)
        
        if existing.get("success") and existing.get("found"):
            # Update existing
            equipment_id = existing["equipment_id"]
            # Remove locationId from update payload (can't change)
            update_data = {k: v for k, v in equipment_data.items() if k != "locationId"}
            result = update_equipment_record(equipment_id, update_data, access_token)
            result["action"] = "updated"
            result["equipment_id"] = equipment_id
            return result
    
    # Create new
    result = create_equipment_record(equipment_data, access_token)
    result["action"] = "created"
    return result


# ============================================================================
# JOB SUMMARY UPDATE
# ============================================================================

def update_job_summary(job_id: int, new_summary: str, access_token: str) -> dict:
    """
    Update the job summary in ServiceTitan.
    """
    url = f"{API_BASE}/jpm/v2/tenant/{TENANT_ID}/jobs/{job_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "summary": new_summary
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code in [200, 204]:
            return {
                "success": True,
                "message": "Job summary updated successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Update failed: {response.status_code} - {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }


def format_equipment_for_summary(
    ocr_data: dict,
    warranty_info: dict,
    equipment_type: str = None
) -> str:
    """
    Format equipment info for job summary.
    Format: Type + Capacity, Serial, Registration + Warranty End Date
    """
    # Handle nested OCR structure
    if "raw_extraction" in ocr_data:
        raw = ocr_data["raw_extraction"]
        derived = ocr_data.get("derived_fields", {})
    else:
        raw = ocr_data
        derived = ocr_data
    
    # Get warranty data
    wd = warranty_info.get("warranty_data", {}) if warranty_info else {}
    
    # Build equipment description
    manufacturer = raw.get("manufacturer", "")
    model_line = raw.get("model_line", "")
    model_number = raw.get("model_number", "")
    
    # Detect type if not provided
    if not equipment_type:
        equipment_type = detect_equipment_type(model_number, manufacturer)
    
    # Build capacity string
    tonnage = derived.get("tonnage") or wd.get("tonnage")
    capacity_btu = derived.get("capacity_btu")
    
    # Format capacity based on equipment type
    if equipment_type in ["Gas Furnace", "Furnace"]:
        if capacity_btu:
            capacity_str = f"{capacity_btu // 1000}K BTU"
        elif tonnage:
            btu = int(tonnage * 12000)
            capacity_str = f"{btu // 1000}K BTU"
        else:
            capacity_str = ""
    else:
        if tonnage:
            capacity_str = f"{tonnage}-Ton"
        else:
            capacity_str = ""
    
    # Build name with capacity
    if model_line:
        equip_name = f"{manufacturer} {model_line}"
    else:
        equip_name = manufacturer
    
    if capacity_str:
        equip_desc = f"{capacity_str} {equipment_type}"
    else:
        equip_desc = equipment_type
    
    if equip_name:
        equip_desc = f"{equip_name} - {equip_desc}"
    
    # Serial number
    serial = raw.get("serial_number", "N/A")
    
    # Determine registration status and warranty end
    is_registered = False
    warranty_end = None
    warranty_years = 5  # Default unregistered
    
    warranty_status = warranty_info.get("lookup_status", "") if warranty_info else ""
    
    if warranty_status == "success" and wd:
        # Check registration type
        reg_type = wd.get("registration_type", "")
        if "base" in reg_type.lower() or "registered" in reg_type.lower():
            is_registered = True
            warranty_years = 10
        
        # Find longest warranty end date from components
        if wd.get("components"):
            latest_end = None
            for comp in wd["components"]:
                try:
                    end_str = comp.get("end_date", "")
                    if end_str:
                        end_dt = datetime.strptime(end_str, "%m/%d/%Y")
                        if latest_end is None or end_dt > latest_end:
                            latest_end = end_dt
                except:
                    pass
            if latest_end:
                warranty_end = latest_end.strftime("%m/%d/%Y")
        
        # Fallback to warranty_end field
        if not warranty_end and wd.get("warranty_end"):
            warranty_end = wd["warranty_end"]
    
    # Build registration/warranty string
    if warranty_end:
        reg_str = "Registered" if is_registered else "Not Registered"
        warranty_str = f"{reg_str} - Warranty until {warranty_end}"
    else:
        warranty_str = "Warranty status unknown"
    
    # Format the summary line
    summary_line = f"• {equip_desc}\n  Serial: {serial}\n  {warranty_str}"
    
    return summary_line


def append_equipment_to_job_summary(
    job_id: int,
    ocr_data: dict,
    warranty_info: dict,
    equipment_type: str,
    access_token: str
) -> dict:
    """
    Append equipment info to job summary.
    Gets current summary, appends new equipment section, updates job.
    """
    # Get current job summary
    job_result = get_job_details(job_id, access_token)
    if not job_result.get("success"):
        return job_result
    
    current_summary = job_result.get("summary", "") or ""
    
    # Format equipment for summary
    equipment_line = format_equipment_for_summary(ocr_data, warranty_info, equipment_type)
    
    # Scanner link for this job
    scanner_url = f"https://christmas-automations.streamlit.app/?job_id={job_id}"
    
    # Check if equipment section already exists
    if "📷 EQUIPMENT ADDED:" in current_summary:
        # Append to existing section (remove old scanner link line if present, we'll re-add at end)
        lines = current_summary.split("\n")
        filtered = [l for l in lines if "➕ Add more:" not in l]
        new_summary = "\n".join(filtered) + "\n" + equipment_line + f"\n➕ Add more: {scanner_url}"
    else:
        # Create new section with scanner link
        new_section = f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n📷 EQUIPMENT ADDED:\n{equipment_line}\n➕ Add more: {scanner_url}"
        new_summary = current_summary + new_section
    
    # Update job summary
    return update_job_summary(job_id, new_summary, access_token)


# ============================================================================
# ATTACHMENT UPLOAD
# ============================================================================

async def upload_equipment_attachment(
    equipment_id: int,
    file_path: str,
    access_token: str,
    file_name: str = None
) -> dict:
    """
    Upload a file (warranty PDF, photo) as an attachment to equipment record.
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    
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
    
    url = f"{API_BASE}/equipmentsystems/v2/tenant/{TENANT_ID}/installed-equipment/attachments"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ST-App-Key": APP_KEY,
    }
    
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        from aiohttp import FormData
        
        data = FormData()
        data.add_field('file', file_bytes, filename=file_name, content_type=content_type)
        data.add_field('installedEquipmentId', str(equipment_id))
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                response_text = await response.text()
                
                if response.status in [200, 201]:
                    return {
                        "success": True,
                        "message": f"Uploaded {file_name} to Equipment {equipment_id}",
                        "response": response_text
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Upload failed: {response.status} - {response_text}"
                    }
    except Exception as e:
        return {
            "success": False,
            "error": f"Upload exception: {str(e)}"
        }


# ============================================================================
# COMPREHENSIVE EQUIPMENT PAYLOAD BUILDER
# ============================================================================

def build_equipment_payload(
    ocr_data: dict,
    warranty_info: dict,
    location_id: int,
    equipment_type_override: str = None
) -> dict:
    """
    Build a comprehensive ServiceTitan equipment payload from OCR and warranty data.
    Fills in ALL available fields.
    """
    # Handle nested OCR structure
    if "raw_extraction" in ocr_data:
        raw = ocr_data["raw_extraction"]
        derived = ocr_data.get("derived_fields", {})
    else:
        raw = ocr_data
        derived = ocr_data
    
    # Get warranty data
    wd = warranty_info.get("warranty_data", {}) if warranty_info else {}
    
    # Build name
    manufacturer = raw.get("manufacturer", "")
    model_line = raw.get("model_line", "")
    model_number = raw.get("model_number", "")
    
    if model_line:
        name = f"{manufacturer} {model_line}".strip()
    else:
        name = f"{manufacturer} {model_number[:10]}".strip() if model_number else manufacturer
    
    # Auto-detect equipment type
    detected_type = detect_equipment_type(
        model_number,
        manufacturer,
        wd.get("product_type")
    )
    equipment_type = equipment_type_override or detected_type
    
    # Build capacity string
    tonnage = derived.get("tonnage") or wd.get("tonnage")
    capacity_btu = derived.get("capacity_btu")
    if tonnage:
        capacity = f"{tonnage} Tons"
        if capacity_btu:
            capacity += f" ({capacity_btu:,} BTU)"
    else:
        capacity = ""
    
    # Parse warranty dates
    install_date = None
    warranty_start = None
    warranty_end = None
    
    # Try warranty data first
    if wd:
        install_date = wd.get("installation_date") or wd.get("install_date") or wd.get("warranty_start")
        warranty_start = wd.get("warranty_start") or install_date
        warranty_end = wd.get("warranty_end")
        
        # Find longest warranty end date from components
        if wd.get("components"):
            latest_end = None
            for comp in wd["components"]:
                try:
                    end_str = comp.get("end_date", "")
                    if end_str:
                        end_dt = datetime.strptime(end_str, "%m/%d/%Y")
                        if latest_end is None or end_dt > latest_end:
                            latest_end = end_dt
                except:
                    pass
            if latest_end:
                warranty_end = latest_end.strftime("%Y-%m-%d")
    
    # Fallback to MFR date if no warranty info
    if not install_date and raw.get("mfr_date"):
        install_date = raw.get("mfr_date")
    
    # Format dates to ISO if in MM/DD/YYYY format
    def format_date(date_str):
        if not date_str:
            return None
        try:
            if "/" in str(date_str):
                dt = datetime.strptime(date_str, "%m/%d/%Y")
                return dt.strftime("%Y-%m-%d")
            return date_str
        except:
            return None
    
    install_date = format_date(install_date)
    warranty_start = format_date(warranty_start) or install_date
    warranty_end = format_date(warranty_end)
    
    # Build comprehensive memo
    memo_parts = []
    
    # OCR info
    if raw.get("refrigerant_type"):
        charge = ""
        if raw.get("refrigerant_charge_lbs") or raw.get("refrigerant_charge_oz"):
            lbs = raw.get("refrigerant_charge_lbs", 0)
            oz = raw.get("refrigerant_charge_oz", 0)
            charge = f" ({lbs}lb {oz}oz)"
        memo_parts.append(f"Refrigerant: {raw['refrigerant_type']}{charge}")
    
    if raw.get("volts"):
        voltage = raw["volts"]
        phase = raw.get("phase", "")
        hz = raw.get("hz", "")
        if phase or hz:
            voltage += f", {phase}ph, {hz}Hz"
        memo_parts.append(f"Voltage: {voltage}")
    
    if raw.get("min_circuit_ampacity"):
        memo_parts.append(f"MCA: {raw['min_circuit_ampacity']}A")
    
    if raw.get("max_fuse_breaker"):
        memo_parts.append(f"Max Breaker: {raw['max_fuse_breaker']}A")
    
    # Warranty components
    if wd.get("components"):
        warranty_notes = []
        for comp in wd["components"][:3]:  # Limit to 3
            comp_name = comp.get("name", "Unknown")
            end = comp.get("end_date", "N/A")
            years = comp.get("term_years", "")
            warranty_notes.append(f"{comp_name}: {end} ({years}yr)")
        memo_parts.append("Warranty: " + ", ".join(warranty_notes))
    
    # Age if calculable
    if wd.get("age_years"):
        memo_parts.append(f"Age: ~{wd['age_years']} years")
    
    # OCR timestamp
    memo_parts.append(f"OCR Processed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Build payload
    payload = {
        "locationId": location_id,
        "name": name[:100] if name else "Unknown Equipment",  # Max length safety
        "manufacturer": manufacturer[:50] if manufacturer else "",
        "model": model_number[:50] if model_number else "",
        "serialNumber": raw.get("serial_number", "")[:50],
        "status": "Installed",
        "memo": " | ".join(memo_parts)[:500],  # Max length safety
    }
    
    # Add optional fields only if they have values
    if equipment_type and equipment_type != "Other":
        payload["type"] = equipment_type
    
    if capacity:
        payload["capacity"] = capacity[:50]
    
    if install_date:
        payload["installedOn"] = install_date
    
    if warranty_start:
        payload["manufacturerWarrantyStart"] = warranty_start
    
    if warranty_end:
        payload["manufacturerWarrantyEnd"] = warranty_end
    
    # Add brand if different from manufacturer (for Carrier family)
    brand = wd.get("brand")
    if brand and brand != manufacturer:
        payload["brand"] = brand
    
    return payload


# ============================================================================
# HIGH-LEVEL WORKFLOW FUNCTION
# ============================================================================

def push_equipment_to_servicetitan(
    ocr_data: dict,
    warranty_info: dict,
    job_id: int,
    equipment_type_override: str = None,
    upload_warranty_file: str = None,
    update_summary: bool = True
) -> dict:
    """
    Complete workflow: Get token, lookup job, create/update equipment, upload attachment, update job summary.
    
    Args:
        ocr_data: Extracted OCR data from data plate
        warranty_info: Warranty lookup result
        job_id: ServiceTitan job ID for location resolution
        equipment_type_override: Optional override for equipment type
        upload_warranty_file: Optional path to warranty PDF/image to attach
        update_summary: Whether to update job summary with equipment info
    
    Returns:
        dict with success status, equipment_id, and details
    """
    result = {
        "success": False,
        "steps": [],
        "equipment_id": None,
        "action": None,
        "error": None
    }
    
    # Step 1: Get token
    token_result = get_servicetitan_token()
    if not token_result.get("success"):
        result["error"] = token_result.get("error", "Token retrieval failed")
        result["steps"].append({"step": "auth", "success": False, "error": result["error"]})
        return result
    
    access_token = token_result["access_token"]
    result["steps"].append({"step": "auth", "success": True})
    
    # Step 2: Get job details for location
    job_result = get_job_details(job_id, access_token)
    if not job_result.get("success"):
        result["error"] = job_result.get("error", "Job lookup failed")
        result["steps"].append({"step": "job_lookup", "success": False, "error": result["error"]})
        return result
    
    location_id = job_result["location_id"]
    result["location_id"] = location_id
    result["customer_id"] = job_result.get("customer_id")
    result["steps"].append({
        "step": "job_lookup",
        "success": True,
        "location_id": location_id,
        "job_number": job_result.get("job_number")
    })
    
    # Step 3: Build equipment payload
    equipment_payload = build_equipment_payload(
        ocr_data,
        warranty_info,
        location_id,
        equipment_type_override
    )
    result["payload"] = equipment_payload
    result["steps"].append({"step": "build_payload", "success": True})
    
    # Step 4: Create or update equipment
    equip_result = create_or_update_equipment(equipment_payload, access_token)
    if not equip_result.get("success"):
        result["error"] = equip_result.get("error", "Equipment creation failed")
        result["steps"].append({"step": "create_equipment", "success": False, "error": result["error"]})
        return result
    
    equipment_id = equip_result.get("equipment_id")
    result["equipment_id"] = equipment_id
    result["action"] = equip_result.get("action", "created")
    result["steps"].append({
        "step": "create_equipment",
        "success": True,
        "equipment_id": equipment_id,
        "action": result["action"]
    })
    
    # Step 5: Upload warranty attachment if provided
    if upload_warranty_file and equipment_id:
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            attach_result = loop.run_until_complete(
                upload_equipment_attachment(equipment_id, upload_warranty_file, access_token)
            )
            loop.close()
            
            result["steps"].append({
                "step": "upload_attachment",
                "success": attach_result.get("success", False),
                "error": attach_result.get("error")
            })
        except Exception as e:
            result["steps"].append({
                "step": "upload_attachment",
                "success": False,
                "error": str(e)
            })
    
    # Step 6: Update job summary with equipment info
    if update_summary:
        summary_result = append_equipment_to_job_summary(
            job_id,
            ocr_data,
            warranty_info,
            equipment_type_override,
            access_token
        )
        result["steps"].append({
            "step": "update_job_summary",
            "success": summary_result.get("success", False),
            "error": summary_result.get("error")
        })
    
    result["success"] = True
    return result

