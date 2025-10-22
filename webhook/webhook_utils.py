import httpx
from datetime import datetime
from schemas import Lead  

async def send_lead_to_webhook(lead: Lead):
    """
    Sends selected lead data to the external CRM webhook.
    Triggered only for certain qualification stages.
    """
    webhook_url = "https://www.thepaulgroup.biz/crm/new_api_to_create_and_assign_leads.php"

    if not lead:
        print("⚠️ No lead provided to webhook.")
        return
    full_name = getattr(lead,'full_name',"")
    first_name = last_name = None
    if full_name:
        name_parts = full_name.strip().split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    # Prepare payload safely
    payload = {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "age": getattr(lead, "age", None),
        "state": getattr(lead, "state_of_residence", None),
        "budget_range": getattr(lead, "budget_range", None),
        "best_contact_time": getattr(lead, "best_contact_time", None),
        "selected_time_slot": getattr(lead, "selected_time_slot", None),
        "ticket_number": getattr(lead, "ticket_number", None),
        "qualification_stage": getattr(lead, "qualification_stage", None),
        "user_id": getattr(lead, "id", None),
        "timestamp": datetime.utcnow().isoformat()
    }

    # Remove None fields
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            print(f"✅ Webhook sent successfully — {response.status_code}")
            print(f"🔹 Response: {response.text[:300]}")  # log short response

            # Try reading JSON safely
            try:
                response_data = response.json()
                print("🟢 Webhook JSON Response:", response_data)
            except Exception:
                print("⚠️ Response is not JSON:", response.text)

    except Exception as e:
        print(f"❌ Error sending webhook: {e}")
