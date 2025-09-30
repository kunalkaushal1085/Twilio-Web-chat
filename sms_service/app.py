from flask import Flask, request, Response,jsonify, abort, url_for
from twilio.twiml.messaging_response import MessagingResponse
from sms_schemas import SMSLead, SMSMessage
import sms_sqlite_utils as db_utils
import json
from file_embaded import answer_from_uploaded_file
from helper import get_available_time_slots, parse_slot_selection
import uuid
from datetime import datetime
import asyncio
import traceback
import os
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from sms_sqlite_utils import (
    initialize_sms_sqlite_db,
    save_lead_to_db,
    get_lead_from_db,
    SMSLead,
    SMSMessage,
    detect_recruiting_inquiry,
    generate_recruiting_response,
    SMSLeadQualificationStage
)

app = Flask(__name__)

# Initialize SMS database
db_utils.initialize_sms_sqlite_db()

# Helper to run async functions in Flask
def run_async(coro):
    return asyncio.run(coro)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

print("ACCOUNT_SID",ACCOUNT_SID)
print("AUTH_TOKEN",AUTH_TOKEN)
print("TWILIO_NUMBER",TWILIO_NUMBER)
if not (ACCOUNT_SID and AUTH_TOKEN and TWILIO_NUMBER):
    raise RuntimeError(
        "Missing Twilio credentials: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_NUMBER "
        "either in a .env (local) or Render Environment Variables (production)"
    )

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Send SMS endpoint
@app.route("/send-sms", methods=["POST"])
def send_sms():
    data = request.get_json(force=True)
    to = data.get("to")
    body = data.get("message")

    if not to or not body:
        return jsonify({"error": "missing 'to' or 'message'"}), 400

    # Get or create lead
    lead = get_lead_from_db(to)
    if not lead:
        lead = SMSLead(
            id=to,  # use phone number as lead ID for consistency
            phone_number=to,
            conversation_history=[]
        )

    # Append outbound message to conversation history
    lead.conversation_history.append(SMSMessage(sender="bot", text=body, timestamp=datetime.now()))

    try:
        # Send SMS via Twilio
        status_cb = url_for("status_callback", _external=True)
        message = client.messages.create(
            body=body,
            from_=TWILIO_NUMBER,
            to=to,
            status_callback=status_cb
        )

        # Save lead with updated conversation history
        save_lead_to_db(lead)

        return jsonify({
            "status": "queued",
            "sid": message.sid,
            "lead_id": lead.id,
            "conversation_history_length": len(lead.conversation_history)
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/receive-sms", methods=["POST", "GET"])
def receive_sms():
    """Receive SMS from Twilio and handle lead updates/responses."""
    # Parse incoming payload
    from_number = request.form.get("From")
    to_number = request.form.get("To")
    body = request.form.get("Body") or request.form.get("SmsBody")

    print(f"📩 Incoming SMS from {from_number}: {body}")

    # Retrieve existing lead if any
    lead = get_lead_from_db(from_number)  # Using phone number as lead ID

    if lead:
        # Append new message to conversation history
        lead.conversation_history.append(
            SMSMessage(sender="user", text=body, timestamp=datetime.now())
        )
    else:
        # Create new lead
        lead = SMSLead(
            id=from_number,
            phone_number=from_number,
            conversation_history=[SMSMessage(sender="user", text=body, timestamp=datetime.now())],
            qualification_stage="initial_chat",
            last_active_timestamp=datetime.now()
        )

    # Detect recruiting inquiries in conversation
    lead.is_recruiting_inquiry = any(
        detect_recruiting_inquiry(msg.text)
        for msg in lead.conversation_history
        if msg.sender == "user"
    )

    # Generate appropriate response
    if lead.is_recruiting_inquiry:
        bot_message = generate_recruiting_response(body)
    else:
        bot_message = "✅ Thanks — we received your message."

    # Append bot response to conversation history
    lead.conversation_history.append(
        SMSMessage(sender="bot", text=bot_message, timestamp=datetime.now())
    )

    # Update last active timestamp
    lead.last_active_timestamp = datetime.now()

    # Save/update lead in SQLite
    save_lead_to_db(lead)

    # Send response back to Twilio
    resp = MessagingResponse()
    resp.message(bot_message)
    return str(resp)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
