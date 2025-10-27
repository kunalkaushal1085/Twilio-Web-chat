import httpx
from datetime import datetime
from schemas import Lead  

async def send_lead_to_webhook(lead: Lead):
    print("inside webhook")

    webhook_url = "https://www.thepaulgroup.biz/crm/new_api_to_create_and_assign_leads.php"

    if not lead:
        print("⚠️ No lead provided to webhook.")
        return

    full_name = getattr(lead, 'full_name', "").strip()

    # Split first and last name
    if " " in full_name:
        name_parts = full_name.split(" ", 1)
        owner_first_name, owner_last_name = name_parts[0], name_parts[1]
    else:
        owner_first_name, owner_last_name = full_name, "Unknown"  # ensure not empty

    # ✅ Match Postman payload keys
    payload = {
        'OwnerFirstName': owner_first_name,
        'OwnerLastName': owner_last_name,
        'phone': getattr(lead, "phone", ""),
        'age': str(getattr(lead, "age", "")),
        'ask_state': getattr(lead, "state_of_residence", ""),  # match Postman key
        'user_id': str(getattr(lead, "id", "")),
    }

    # Remove None or empty keys
    payload = {k: v for k, v in payload.items() if v}

    print("📤 Payload Sent:", payload)

    try:
        # ✅ send as multipart/form-data like Postman
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, data=payload)
            print("Content-Type:", response.request.headers.get("Content-Type"))
            print(f"✅ Webhook sent successfully — {response.status_code}")
            print(f"🔹 Response: {response.text[:300]}")

            try:
                response_data = response.json()
                print("🟢 Webhook JSON Response:", response_data)
                return response_data
            except Exception:
                print("⚠️ Response is not JSON:", response.text)
                return None

    except Exception as e:
        print(f"❌ Error sending webhook: {e}")
        return None
