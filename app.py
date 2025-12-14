
import streamlit as st
import os
import asyncio
import json
from PIL import Image
import google.generativeai as genai
from equipment_poc import lookup_warranty
from servicetitan_api import (
    get_servicetitan_token,
    get_job_details,
    detect_equipment_type,
    get_all_equipment_types,
    push_equipment_to_servicetitan,
)

# Page Config
st.set_page_config(
    page_title="Equipment OCR",
    page_icon="📸",
    layout="wide"
)

# ============================================================================
# API KEY LOADING
# ============================================================================

def get_gemini_api_key():
    """Get Gemini API key from secrets (production) or file (local dev)."""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    KEY_FILE = "gemini_key.txt"
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            return f.read().strip()
    return None

api_key = get_gemini_api_key()
if not api_key:
    st.error("⚠️ Gemini API Key not configured.")
    st.stop()

genai.configure(api_key=api_key)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def process_single_image(image, model):
    """OCR a single image."""
    prompt = """
    Analyze this HVAC equipment data plate. Extract:
    - Manufacturer, Model Number, Serial Number, Model Line
    - Manufacture Date, Refrigerant Type
    - Tonnage (from model number if possible), BTU capacity
    
    Return JSON:
    {
        "is_data_plate": true,
        "raw_extraction": {
            "manufacturer": "", "model_line": "", "model_number": "",
            "serial_number": "", "mfr_date": "", "refrigerant_type": "",
            "refrigerant_charge_lbs": 0, "refrigerant_charge_oz": 0
        },
        "derived_fields": { "tonnage": 0, "capacity_btu": 0 }
    }
    Return only valid JSON.
    """
    response = model.generate_content([prompt, image])
    text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def run_warranty_lookup(serial, manufacturer):
    """Run async warranty lookup."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(lookup_warranty(serial, manufacturer))
    loop.close()
    return result

# ============================================================================
# CHECK FOR TECH MODE (URL parameter)
# ============================================================================

query_params = st.query_params
url_job_id = query_params.get("job_id")
tech_mode = url_job_id is not None


# ============================================================================
# TECH MODE - Minimal mobile interface
# ============================================================================

if tech_mode:
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        .stButton > button { width: 100%; padding: 1rem; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("📷 Scan Equipment")
    
    job_id = int(url_job_id)
    
    # Get job info
    if "tech_job" not in st.session_state:
        token = get_servicetitan_token()
        if token.get("success"):
            job = get_job_details(job_id, token["access_token"])
            if job.get("success"):
                st.session_state.tech_job = job
            else:
                st.error(f"Job not found: {job.get('error')}")
                st.stop()
    
    st.info(f"📋 Job #{st.session_state.tech_job.get('job_number', job_id)}")
    
    # Camera + Upload
    camera_img = st.camera_input("Take photo")
    uploaded_img = st.file_uploader("Or upload", type=['jpg', 'jpeg', 'png'])
    
    image = Image.open(camera_img) if camera_img else (Image.open(uploaded_img) if uploaded_img else None)
    
    if image:
        st.image(image, use_container_width=True)
        
        if st.button("🔍 SCAN & ADD", type="primary"):
            with st.spinner("Processing..."):
                try:
                    model = genai.GenerativeModel("models/gemini-1.5-flash")
                    data = process_single_image(image, model)
                    
                    if not data.get("is_data_plate"):
                        st.error("Not a data plate")
                        st.stop()
                    
                    serial = data["raw_extraction"].get("serial_number")
                    mfr = data["raw_extraction"].get("manufacturer", "")
                    warranty = run_warranty_lookup(serial, mfr) if serial else {}
                    
                    eq_type = detect_equipment_type(data["raw_extraction"].get("model_number", ""), mfr)
                    
                    result = push_equipment_to_servicetitan(data, warranty, job_id, eq_type, update_summary=True)
                    
                    if result.get("success"):
                        st.success(f"✅ Added! ID: {result.get('equipment_id')}")
                        st.balloons()
                    else:
                        st.error(result.get("error"))
                except Exception as e:
                    st.error(str(e))

else:
    # ============================================================================
    # OFFICE MODE - Full interface, unified upload
    # ============================================================================
    
    st.title("📷 Equipment OCR & Warranty")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        st.success("✅ API Connected")
        
        st.divider()
        
        # Job ID input
        st.header("📋 Job")
        job_id = st.number_input("Job ID", min_value=1, step=1, key="job_id")
        
        if job_id and st.button("🔍 Lookup"):
            token = get_servicetitan_token()
            if token.get("success"):
                job = get_job_details(int(job_id), token["access_token"])
                if job.get("success"):
                    st.session_state.job = job
                    st.success(f"✅ #{job.get('job_number')}")
                else:
                    st.error("Not found")
        
        if st.session_state.get("job"):
            st.caption(f"Location: {st.session_state.job.get('location_id')}")
        
        st.divider()
        
        # Link generator
        st.header("📱 Tech Link")
        try:
            app_url = st.secrets.get("APP_URL", "https://christmasautomations.streamlit.app")
        except:
            app_url = "http://localhost:8501"
        
        if job_id:
            st.code(f"{app_url}/?job_id={job_id}")
    
    # Main area - unified upload
    st.markdown("### Upload data plate photos (1 or more)")
    
    uploaded_files = st.file_uploader(
        "Drop photos here",
        type=['jpg', 'jpeg', 'png'],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    
    # Manual serial entry option
    with st.expander("⌨️ Or enter serial manually"):
        col1, col2 = st.columns(2)
        with col1:
            man_serial = st.text_input("Serial Number")
        with col2:
            man_mfr = st.selectbox("Manufacturer", ["Trane", "American Standard", "Carrier", "Other"])
        
        if st.button("Lookup Warranty") and man_serial:
            with st.spinner("Looking up..."):
                warranty = run_warranty_lookup(man_serial, man_mfr)
            st.json(warranty.get("warranty_data", {}))
    
    # Show uploaded images
    if uploaded_files:
        st.markdown(f"### {len(uploaded_files)} photo(s) ready")
        
        # Show thumbnails
        cols = st.columns(min(len(uploaded_files), 4))
        for i, f in enumerate(uploaded_files[:4]):
            with cols[i]:
                st.image(Image.open(f), use_container_width=True)
        
        if len(uploaded_files) > 4:
            st.caption(f"... and {len(uploaded_files) - 4} more")
        
        # Process button
        update_summary = st.checkbox("📝 Update job summary", value=True)
        
        process_btn = st.button(
            f"🚀 Process {'All ' + str(len(uploaded_files)) + ' Photos' if len(uploaded_files) > 1 else 'Photo'}",
            type="primary",
            disabled=not st.session_state.get("job")
        )
        
        if not st.session_state.get("job"):
            st.warning("⚠️ Enter a Job ID in the sidebar first")
        
        if process_btn:
            results = []
            progress = st.progress(0)
            status = st.empty()
            
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            
            for i, f in enumerate(uploaded_files):
                status.text(f"Processing {i+1}/{len(uploaded_files)}: {f.name}")
                progress.progress((i + 1) / len(uploaded_files))
                
                try:
                    img = Image.open(f)
                    
                    # OCR
                    data = process_single_image(img, model)
                    
                    if not data.get("is_data_plate"):
                        results.append({"file": f.name, "success": False, "error": "Not a data plate"})
                        continue
                    
                    raw = data["raw_extraction"]
                    
                    # Warranty lookup
                    serial = raw.get("serial_number")
                    mfr = raw.get("manufacturer", "")
                    warranty = run_warranty_lookup(serial, mfr) if serial else {}
                    
                    # Detect type
                    eq_type = detect_equipment_type(raw.get("model_number", ""), mfr)
                    
                    # Push to ServiceTitan
                    push_result = push_equipment_to_servicetitan(
                        data, warranty, int(job_id), eq_type, update_summary=update_summary
                    )
                    
                    results.append({
                        "file": f.name,
                        "success": push_result.get("success"),
                        "equipment_id": push_result.get("equipment_id"),
                        "manufacturer": mfr,
                        "serial": serial,
                        "type": eq_type,
                        "error": push_result.get("error")
                    })
                    
                except Exception as e:
                    results.append({"file": f.name, "success": False, "error": str(e)})
            
            progress.empty()
            status.empty()
            
            # Show results
            success_count = sum(1 for r in results if r.get("success"))
            
            if success_count == len(results):
                st.success(f"✅ All {success_count} equipment records created!")
                st.balloons()
            elif success_count > 0:
                st.warning(f"⚠️ {success_count}/{len(results)} succeeded")
            else:
                st.error("❌ All failed")
            
            # Results table
            for r in results:
                if r.get("success"):
                    st.markdown(f"✅ **{r.get('manufacturer', '')}** - {r.get('type', '')} | Serial: {r.get('serial', 'N/A')} | ID: {r.get('equipment_id')}")
                else:
                    st.markdown(f"❌ {r.get('file')}: {r.get('error')}")
