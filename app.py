
import streamlit as st
import os
import asyncio
import json
import pandas as pd
from PIL import Image
import google.generativeai as genai
from equipment_poc import lookup_warranty, format_for_servicetitan, generate_report
from servicetitan_api import (
    get_servicetitan_token,
    get_job_details,
    get_location_details,
    get_existing_equipment,
    detect_equipment_type,
    get_all_equipment_types,
    build_equipment_payload,
    create_or_update_equipment,
    push_equipment_to_servicetitan,
    upload_equipment_attachment,
    append_equipment_to_job_summary
)

# Page Config
st.set_page_config(
    page_title="Equipment OCR & Warranty",
    page_icon="📸",
    layout="wide"
)

# Check for URL parameters (job_id for integration mode)
query_params = st.query_params
url_job_id = query_params.get("job_id")
tech_mode = url_job_id is not None  # Tech/mobile mode if job_id in URL


# ============================================================================
# TECH MODE (Mobile-friendly, linked from ServiceTitan)
# ============================================================================

if tech_mode:
    # Minimal mobile-friendly interface
    st.markdown("""
    <style>
        .main-header { font-size: 1.8rem; color: #3366cc; text-align: center; }
        .job-info { background: #e3f2fd; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
        .stButton > button { width: 100%; padding: 1rem; font-size: 1.2rem; }
        .success-msg { background: #c8e6c9; padding: 1rem; border-radius: 8px; text-align: center; }
        .stFileUploader { border: 2px dashed #3366cc; border-radius: 12px; padding: 2rem; }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-header">📷 Scan Data Plate</div>', unsafe_allow_html=True)
    
    # API Key (load from file silently)
    KEY_FILE = "gemini_key.txt"
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            api_key = f.read().strip()
        genai.configure(api_key=api_key)
    else:
        st.error("API Key not configured. Please contact admin.")
        st.stop()
    
    # Validate job and get info
    job_id = int(url_job_id)
    
    if "tech_job_info" not in st.session_state:
        token_result = get_servicetitan_token()
        if token_result.get("success"):
            job_result = get_job_details(job_id, token_result["access_token"])
            if job_result.get("success"):
                st.session_state.tech_job_info = job_result
            else:
                st.error(f"Job not found: {job_result.get('error')}")
                st.stop()
        else:
            st.error("Could not connect to ServiceTitan")
            st.stop()
    
    job_info = st.session_state.tech_job_info
    
    # Show job info
    st.markdown(f'''
    <div class="job-info">
        <strong>Job #{job_info.get("job_number", job_id)}</strong><br>
        📍 Location ID: {job_info.get("location_id")}
    </div>
    ''', unsafe_allow_html=True)
    
    # Camera/file upload (camera_input for mobile)
    st.markdown("### Take a photo of the data plate:")
    
    # Use camera on mobile, file uploader as fallback
    camera_image = st.camera_input("📸 Capture Data Plate", label_visibility="collapsed")
    
    st.markdown("---")
    st.markdown("Or upload an existing photo:")
    uploaded_image = st.file_uploader("Upload Image", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
    
    # Use whichever image is available
    image = None
    if camera_image:
        image = Image.open(camera_image)
    elif uploaded_image:
        image = Image.open(uploaded_image)
    
    if image:
        st.image(image, caption="Data Plate", use_container_width=True)
        
        if st.button("🔍 SCAN & ADD EQUIPMENT", type="primary"):
            with st.status("Processing...", expanded=True) as status:
                try:
                    # OCR
                    status.write("🔍 Analyzing data plate...")
                    model = genai.GenerativeModel("models/gemini-1.5-flash")
                    prompt = """
                    Analyze this HVAC equipment data plate. Extract:
                    - Manufacturer, Model Number, Serial Number
                    - Manufacture Date, Refrigerant Type
                    - Tonnage (from model number if possible)
                    - BTU capacity if shown
                    
                    Return JSON:
                    {
                        "is_data_plate": true,
                        "raw_extraction": {
                            "manufacturer": "...",
                            "model_line": "...",
                            "model_number": "...",
                            "serial_number": "...",
                            "mfr_date": "...",
                            "refrigerant_type": "...",
                            "refrigerant_charge_lbs": 0,
                            "refrigerant_charge_oz": 0
                        },
                        "derived_fields": { "tonnage": 0, "capacity_btu": 0 }
                    }
                    Return only valid JSON.
                    """
                    response = model.generate_content([prompt, image])
                    text = response.text.replace("```json", "").replace("```", "").strip()
                    extracted_data = json.loads(text)
                    
                    if not extracted_data.get("is_data_plate"):
                        status.update(label="Not a Data Plate", state="error")
                        st.error("Could not read data plate. Try a clearer photo.")
                        st.stop()
                    
                    status.write("✅ Data extracted!")
                    
                    # Warranty lookup
                    serial = extracted_data["raw_extraction"].get("serial_number")
                    manufacturer = extracted_data["raw_extraction"].get("manufacturer", "")
                    
                    status.write("🌐 Looking up warranty...")
                    if serial:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        warranty_info = loop.run_until_complete(lookup_warranty(serial, manufacturer))
                        loop.close()
                        status.write(f"✅ Warranty: {warranty_info.get('lookup_status', 'N/A')}")
                    else:
                        warranty_info = {"lookup_status": "skipped"}
                    
                    # Auto-detect equipment type
                    model_num = extracted_data["raw_extraction"].get("model_number", "")
                    equipment_type = detect_equipment_type(model_num, manufacturer)
                    
                    # Push to ServiceTitan
                    status.write("📤 Creating equipment record...")
                    result = push_equipment_to_servicetitan(
                        extracted_data,
                        warranty_info,
                        job_id,
                        equipment_type,
                        update_summary=True  # Write to job summary
                    )
                    
                    if result.get("success"):
                        status.update(label="✅ Equipment Added!", state="complete")
                    else:
                        status.update(label="Error", state="error")
                        st.error(result.get("error", "Failed to create equipment"))
                        st.stop()
                        
                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"Error: {str(e)}")
                    st.stop()
            
            # Success display
            raw = extracted_data["raw_extraction"]
            derived = extracted_data.get("derived_fields", {})
            
            st.markdown(f'''
            <div class="success-msg">
                <h3>✅ Equipment Added!</h3>
                <p><strong>{raw.get("manufacturer", "")} {raw.get("model_line", "")}</strong></p>
                <p>Serial: {raw.get("serial_number", "N/A")}</p>
                <p>Type: {equipment_type}</p>
                <p>Equipment ID: {result.get("equipment_id")}</p>
            </div>
            ''', unsafe_allow_html=True)
            
            st.success("📝 Job summary updated!")
            
            # Done button
            st.markdown("---")
            if st.button("✅ DONE - Back to ServiceTitan"):
                st.markdown("You can close this window and return to ServiceTitan.")

else:
    # ============================================================================
    # FULL MODE (Office use, with all features)
    # ============================================================================
    
    # Styling
    st.markdown("""
    <style>
        .main-header { font-size: 2.5rem; color: #3366cc; }
        .sub-header { font-size: 1.5rem; color: #666; }
        .success-box { padding: 1rem; background-color: #d4edda; border-radius: 5px; color: #155724; }
        .warning-box { padding: 1rem; background-color: #fff3cd; border-radius: 5px; color: #856404; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-header">Equipment OCR & Warranty Lookup</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Powered by Google Gemini Vision + ServiceTitan Integration</div>', unsafe_allow_html=True)
    st.divider()

    # Sidebar - Configuration
    with st.sidebar:
        st.header("Configuration")
        
        KEY_FILE = "gemini_key.txt"
        saved_key = ""
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, "r") as f:
                saved_key = f.read().strip()
                
        api_key = st.text_input("Google Gemini API Key", value=saved_key, type="password")
        
        save_key = st.checkbox("Save API Key", value=bool(saved_key))
        
        if save_key and api_key:
            with open(KEY_FILE, "w") as f:
                f.write(api_key)
        elif not save_key and os.path.exists(KEY_FILE):
            os.remove(KEY_FILE)
        
        if not api_key:
            st.warning("Please enter your Gemini API Key.")
            st.stop()
            
        st.success("API Key provided!")
        genai.configure(api_key=api_key)
        
        st.divider()
        st.header("ServiceTitan")
        
        if st.button("🔌 Test Connection"):
            with st.spinner("Testing..."):
                token_result = get_servicetitan_token()
                if token_result.get("success"):
                    st.success("✅ Connected!")
                else:
                    st.error(f"❌ {token_result.get('error')}")
        
        # Link generator for techs
        st.divider()
        st.header("📱 Tech Link Generator")
        link_job_id = st.text_input("Job ID for link:", key="link_gen_job")
        if link_job_id:
            # For demo, use localhost. Replace with real URL when deployed
            base_url = "http://localhost:8501"
            tech_link = f"{base_url}/?job_id={link_job_id}"
            st.code(tech_link, language=None)
            st.info("Add this link to job summary template")

    # Main tabs
    tab_upload, tab_batch, tab_manual = st.tabs(["📷 Single Upload", "📷📷📷 Batch Mode", "⌨️ Manual Lookup"])

    # --- SINGLE UPLOAD TAB ---
    with tab_upload:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.header("1. Upload Photo")
            uploaded_file = st.file_uploader("Upload Data Plate Image", type=['jpg', 'jpeg', 'png'], key="single_upload")
            
            if uploaded_file:
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Image", use_container_width=True)

        with col2:
            st.header("2. Analysis Results")
            
            if uploaded_file and st.button("Analyze & Lookup Warranty", type="primary", key="single_analyze"):
                with st.status("Processing...", expanded=True) as status:
                    try:
                        status.write("🔍 Analyzing with Gemini...")
                        model = genai.GenerativeModel("models/gemini-1.5-flash")
                        
                        prompt = """
                        Analyze this HVAC data plate. Extract all visible info into JSON:
                        {
                            "is_data_plate": true,
                            "raw_extraction": {
                                "manufacturer": "", "model_line": "", "model_number": "",
                                "serial_number": "", "mfr_date": "", "refrigerant_type": "",
                                "refrigerant_charge_lbs": 0, "refrigerant_charge_oz": 0,
                                "volts": "", "phase": 1, "hz": 60,
                                "min_circuit_ampacity": 0, "max_fuse_breaker": 0
                            },
                            "derived_fields": { "tonnage": 0, "capacity_btu": 0 }
                        }
                        Return only valid JSON.
                        """
                        
                        response = model.generate_content([prompt, image])
                        text = response.text.replace("```json", "").replace("```", "").strip()
                        extracted_data = json.loads(text)
                        status.write("✅ OCR Complete!")
                        
                        if not extracted_data.get("is_data_plate"):
                            status.update(label="Not a Data Plate", state="error")
                            st.error("Not a data plate")
                            st.stop()
                        
                        # Warranty lookup
                        status.write("🌐 Looking up warranty...")
                        serial = extracted_data["raw_extraction"].get("serial_number")
                        manufacturer = extracted_data["raw_extraction"].get("manufacturer", "")
                        
                        if serial:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            warranty_info = loop.run_until_complete(lookup_warranty(serial, manufacturer))
                            loop.close()
                            status.write(f"✅ Warranty: {warranty_info.get('lookup_status')}")
                        else:
                            warranty_info = {"lookup_status": "skipped"}
                        
                        status.update(label="Done!", state="complete")
                        
                    except Exception as e:
                        status.update(label="Error", state="error")
                        st.error(f"Error: {e}")
                        st.stop()
                
                # Store results
                st.session_state.single_extracted = extracted_data
                st.session_state.single_warranty = warranty_info
                
                # Display extracted data
                raw = extracted_data.get("raw_extraction", {})
                cols = st.columns(2)
                with cols[0]:
                    st.subheader("Extracted Data")
                    for k, v in list(raw.items())[:8]:
                        if v:
                            st.text(f"{k}: {v}")
                with cols[1]:
                    st.subheader("Warranty")
                    st.text(f"Status: {warranty_info.get('lookup_status', 'N/A')}")
                    wd = warranty_info.get("warranty_data", {})
                    for k, v in list(wd.items())[:5]:
                        if v and k != "components":
                            st.text(f"{k}: {v}")
                
                # ServiceTitan Push
                st.divider()
                st.header("3. Push to ServiceTitan")
                
                job_col, type_col = st.columns(2)
                with job_col:
                    job_id = st.number_input("Job ID", min_value=1, step=1, key="single_job")
                    if st.button("🔍 Lookup Job"):
                        token = get_servicetitan_token()
                        if token.get("success"):
                            job = get_job_details(int(job_id), token["access_token"])
                            if job.get("success"):
                                st.session_state.job_info = job
                                st.success(f"✅ Job #{job.get('job_number')}")
                
                with type_col:
                    model_num = raw.get("model_number", "")
                    detected = detect_equipment_type(model_num, raw.get("manufacturer"))
                    all_types = get_all_equipment_types()
                    idx = all_types.index(detected) if detected in all_types else 0
                    equipment_type = st.selectbox("Equipment Type", all_types, index=idx)
                
                update_summary = st.checkbox("📝 Update job summary", value=True)
                
                if st.button("🚀 Create Equipment", type="primary", disabled=not st.session_state.get("job_info")):
                    with st.spinner("Creating..."):
                        result = push_equipment_to_servicetitan(
                            extracted_data, warranty_info, int(job_id),
                            equipment_type, update_summary=update_summary
                        )
                    if result.get("success"):
                        st.success(f"✅ Equipment {result.get('action')}! ID: {result.get('equipment_id')}")
                        if update_summary:
                            st.info("📝 Job summary updated!")
                    else:
                        st.error(result.get("error"))

    # --- BATCH MODE TAB ---
    with tab_batch:
        st.header("📷 Batch Processing")
        st.info("Upload multiple data plate photos to process at once.")
        
        batch_job_id = st.number_input("Job ID (required)", min_value=1, step=1, key="batch_job")
        
        if batch_job_id and st.button("🔍 Lookup Job", key="batch_lookup"):
            token = get_servicetitan_token()
            if token.get("success"):
                job = get_job_details(int(batch_job_id), token["access_token"])
                if job.get("success"):
                    st.session_state.batch_job = job
                    st.success(f"✅ Job #{job.get('job_number')}")
        
        batch_files = st.file_uploader("Upload Images", type=['jpg', 'jpeg', 'png'], 
                                       accept_multiple_files=True, key="batch_files")
        
        if batch_files and st.button("🔄 Process All", type="primary"):
            results = []
            progress = st.progress(0)
            
            for i, f in enumerate(batch_files):
                progress.progress((i+1)/len(batch_files))
                try:
                    img = Image.open(f)
                    model = genai.GenerativeModel("models/gemini-1.5-flash")
                    prompt = "Extract HVAC data plate info as JSON with is_data_plate, raw_extraction, derived_fields"
                    resp = model.generate_content([prompt, img])
                    data = json.loads(resp.text.replace("```json", "").replace("```", "").strip())
                    
                    if data.get("is_data_plate"):
                        serial = data["raw_extraction"].get("serial_number")
                        mfr = data["raw_extraction"].get("manufacturer")
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        warranty = loop.run_until_complete(lookup_warranty(serial, mfr)) if serial else {}
                        loop.close()
                        
                        results.append({"file": f.name, "data": data, "warranty": warranty, "success": True})
                except Exception as e:
                    results.append({"file": f.name, "error": str(e), "success": False})
            
            st.session_state.batch_results = results
            st.success(f"Processed {len(results)} images")
        
        if st.session_state.get("batch_results") and st.session_state.get("batch_job"):
            if st.button("🚀 Push All to ServiceTitan", type="primary"):
                for r in [x for x in st.session_state.batch_results if x.get("success")]:
                    model_num = r["data"]["raw_extraction"].get("model_number", "")
                    eq_type = detect_equipment_type(model_num)
                    push_equipment_to_servicetitan(
                        r["data"], r.get("warranty", {}), int(batch_job_id), eq_type, update_summary=True
                    )
                st.success("✅ All equipment pushed!")

    # --- MANUAL LOOKUP TAB ---
    with tab_manual:
        st.header("Manual Warranty Lookup")
        
        col1, col2 = st.columns(2)
        with col1:
            man_serial = st.text_input("Serial Number")
        with col2:
            man_mfr = st.selectbox("Manufacturer", ["Trane", "American Standard", "Carrier", "Other"])
        
        if st.button("Lookup Warranty", type="primary") and man_serial:
            with st.spinner("Looking up..."):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                warranty = loop.run_until_complete(lookup_warranty(man_serial, man_mfr))
                loop.close()
            
            st.subheader(f"Status: {warranty.get('lookup_status', 'Unknown').upper()}")
            
            if warranty.get("pdf_url"):
                st.link_button("📄 Open Warranty", warranty["pdf_url"])
            
            if warranty.get("warranty_data"):
                st.json(warranty["warranty_data"])
