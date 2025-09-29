from flask import Flask, request, Response
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
