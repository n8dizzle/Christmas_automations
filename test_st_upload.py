"""
Test ServiceTitan Attachment Upload
"""
import asyncio
import requests
import os
from servicetitan_config import *
from equipment_poc import upload_warranty_to_servicetitan

def get_access_token():
    """Get OAuth2 access token from ServiceTitan"""
    response = requests.post(
        AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        print(f"✓ Got access token: {token[:20]}...")
        return token
    else:
        print(f"✗ Failed to get token: {response.status_code}")
        print(response.text)
        return None


async def test_upload(job_id: int, file_path: str):
    """Test uploading a file to a job"""
    
    print(f"\n{'='*50}")
    print(f"  Testing ServiceTitan Attachment Upload")
    print(f"{'='*50}\n")
    
    # Get token
    token = get_access_token()
    if not token:
        return
    
    # Upload
    print(f"\n→ Uploading {file_path} to Job {job_id}...")
    
    result = await upload_warranty_to_servicetitan(
        job_id=job_id,
        file_path=file_path,
        tenant_id=TENANT_ID,
        access_token=token,
        file_name="Warranty_Document.png",
        attachment_type="Other",
        app_key=APP_KEY
    )
    
    print(f"\n→ Result: {result}")
    return result


if __name__ == "__main__":
    import sys
    
    # Default test values
    job_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    file_path = "./warranty_output/warranty_5434REB2F_doc.png"
    
    if not job_id:
        print("Usage: python3 test_upload.py <JOB_ID>")
        print("\nExample: python3 test_upload.py 12345678")
        print("\nPick an old completed job ID from ServiceTitan to test with.")
    else:
        asyncio.run(test_upload(job_id, file_path))
