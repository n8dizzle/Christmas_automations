# ServiceTitan API Configuration
# Supports both Streamlit Cloud secrets and local development

import os

# Try to use Streamlit secrets (for cloud deployment)
try:
    import streamlit as st
    TENANT_ID = st.secrets.get("TENANT_ID", os.getenv("TENANT_ID"))
    CLIENT_ID = st.secrets.get("CLIENT_ID", os.getenv("CLIENT_ID"))
    CLIENT_SECRET = st.secrets.get("CLIENT_SECRET", os.getenv("CLIENT_SECRET"))
    APP_KEY = st.secrets.get("APP_KEY", os.getenv("APP_KEY"))
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
except:
    # Fallback for non-Streamlit environments or local dev
    TENANT_ID = os.getenv("TENANT_ID")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    APP_KEY = os.getenv("APP_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Local development fallbacks (override with your values)
if not TENANT_ID:
    TENANT_ID = "1045848487"
if not CLIENT_ID:
    CLIENT_ID = "cid.t1lk0gh2gztvleub8kp4a2jmo"
if not CLIENT_SECRET:
    CLIENT_SECRET = "cs2.6yb7m7hh09wa4huzz0urjwe7tk9gl0v3ik7xyvk3ggjgwc810e"
if not APP_KEY:
    APP_KEY = "ak1.fscoe5xled3zhbbzcnxjeimyx"

# API Endpoints (Production)
API_BASE = "https://api.servicetitan.io"
AUTH_URL = "https://auth.servicetitan.io/connect/token"
