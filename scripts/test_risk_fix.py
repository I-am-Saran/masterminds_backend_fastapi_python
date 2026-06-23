import requests
import json
from uuid import uuid4
from datetime import date

BASE_URL = "http://127.0.0.1:8000/api"

def test_risk_flow():
    print("Testing Risk Register Flow...")
    
    try:
        # 0. Get a valid Organization ID
        print("Fetching organizations...")
        org_res = requests.get(f"{BASE_URL}/organizations")
        if org_res.status_code != 200:
            print(f"Failed to get organizations: {org_res.text}")
            return
            
        orgs = org_res.json().get('data', [])
        if not orgs:
            print("No organizations found. Cannot create risk.")
            return
            
        org_id = orgs[0]['id']
        print(f"Using Organization ID: {org_id}")

        # 1. Create a Risk
        payload = {
            "organization_id": org_id, 
            "risk_title": "Test Risk from Script",
            "risk_description": "Created to verify fix",
            "category": "Operational",
            "likelihood": 3,
            "impact": 3,
            "mitigation_plan": "Test plan",
            "status": "Open",
            "owner": "test@example.com",
            "created_by": "script_runner",
            "tenant_id": "00000000-0000-0000-0000-000000000001"
        }
        
        print("Creating risk...")
        response = requests.post(f"{BASE_URL}/risk-register", json=payload)
        print(f"Create Risk Status: {response.status_code}")
        
        risk_id = None
        if response.status_code == 200:
            print("Create Risk Response:", response.json())
            risk_id = response.json()['data']['id']
        else:
            print("Create Risk Error:", response.text)
            return

        # 2. List Risks (No Org Filter)
        print("Listing risks...")
        response = requests.get(f"{BASE_URL}/risk-register")
        print(f"List Risks Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()['data']
            print(f"Risks Found: {len(data)}")
            found = any(r['id'] == risk_id for r in data)
            print(f"Newly created risk found in list: {found}")
            if found:
                print("SUCCESS: Risk created and fetched.")
            else:
                print("FAILURE: Risk created but not found in list.")
        else:
            print("List Risks Error:", response.text)

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_risk_flow()
