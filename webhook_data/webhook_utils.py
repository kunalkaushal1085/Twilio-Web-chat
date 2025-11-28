import httpx
from datetime import datetime
from schemas import Lead  
import json
import os

async def send_lead_to_webhook(lead: Lead):
    print("inside webhook", lead)

    webhook_url = "https://www.thepaulgroup.biz/crm/new_api_to_create_and_assign_leads.php"

    if not lead or not lead.full_name:
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


async def send_chat_summary_to_webhook(lead_id:str , conversation_history:list):
    """
    Sends the chat conversation summary to the CRM once lead_id is received.
    """
    if not lead_id:
        print("⚠️ No lead_id provided, skipping summary send.")
        return
    webhook_url = "https://www.thepaulgroup.biz/crm/new_api_to_receive_text_summary.php"
    # Format conversation for clarity
    formatted_history = "\n".join(
        [f"{msg.sender.upper()}: {msg.text}" for msg in conversation_history]
    )
    payload = {
        "id": lead_id,
        "text_summary": formatted_history
    }
    print("📤 Sending chat summary payload:", json.dumps(payload, indent=2))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, data=payload)
            print(f"✅ Summary sent — Status: {response.status_code}")
            print(f"🔹 Response: {response.text[:5000]}")
            os.makedirs("webhook_logs", exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = f"webhook_logs/chat_summary_{lead_id}_{timestamp}.json"
            try:
                response_data = response.json()
                print("🟢 Summary Webhook JSON Response:", response_data)
                # return response_data
            except Exception:
                print("⚠️ Summary Response not JSON:", response.text)
                # return None
                response_data = {"raw_text": response.text}
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump({
                    "webhook_url": webhook_url,
                    "payload_sent": payload,
                    "response_received": response_data
                }, f, indent=2, ensure_ascii=False)

            print(f"🗂️ Full webhook response saved to: {log_file}")
            return response_data
    except Exception as e:
        print(f"❌ Error sending summary webhook: {e}")
        return None