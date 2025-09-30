import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, abort, url_for
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from file_embaded import answer_from_uploaded_file
from sms_schemas import SMSLead, SMSMessageSchema, SMSChatResponseSchema
from sms_sqlite_utils import (
    get_lead_from_db, save_lead_to_db, get_all_leads_from_db,
    detect_recruiting_inquiry, generate_recruiting_response,
    ensure_admin_table,store_uploaded_file_info,store_versioned_dataset, get_active_dataset_version, 
    get_all_dataset_versions, set_active_dataset_version,ensure_welcome_table,
    get_welcome_message,
    store_uploaded_file_info, ensure_dataset_versions_table,
    initialize_sms_sqlite_db
)
import asyncio

# # Load local .env only if present (safe for dev)
load_dotenv()

# # Twilio credentials (from Render ENV or .env locally)
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

print("ACCOUNT_SID",ACCOUNT_SID)
print("AUTH_TOKEN",AUTH_TOKEN)
print("TWILIO_NUMBER",TWILIO_NUMBER)
if not (ACCOUNT_SID and AUTH_TOKEN and TWILIO_NUMBER):
    raise RuntimeError(
        "Missing Twilio credentials: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_NUMBER "
        "either in a .env (local) or Render Environment Variables (production)"
    )


client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Flask app and DB
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sms.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# DB model
# class Message(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     sid = db.Column(db.String(64), index=True, nullable=True)
#     from_number = db.Column(db.String(32))
#     to_number = db.Column(db.String(32))
#     body = db.Column(db.Text)
#     direction = db.Column(db.String(10))  # 'inbound' or 'outbound'
#     status = db.Column(db.String(32), default="received")
#     error_code = db.Column(db.String(32), nullable=True)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow)


@app.before_request
def on_startup():
    ensure_admin_table()
    ensure_welcome_table()
    initialize_sms_sqlite_db()
    # store_uploaded_file_info()
    # ensure_dataset_versions_table()
    # ensure_quicklink_table()
    # ensure_theme_table()
    # ensure_appointment_table()


# Send SMS endpoint
@app.route("/send-sms", methods=["POST"])
async def send_sms():
    data = request.get_json(force=True)
    to = data.get("to")
    body = data.get("message")
    if not to or not body:
        return jsonify({"error": "missing 'to' or 'message'"}), 400

    # Status callback URL for delivery updates
    status_cb = url_for("status_callback", _external=True)
    message = client.messages.create(
        body=body, from_=TWILIO_NUMBER, to=to, status_callback=status_cb
    )

    # Save outbound message
    # db_msg = SMSMessageSchema(
    #     sid=message.sid,
    #     from_number=TWILIO_NUMBER,
    #     to_number=to,
    #     body=body,
    #     direction="outbound",
    #     status=message.status,
    # )
    # db.session.add(db_msg)
    # db.session.commit()

    lead = SMSLead(id=message.sid, qualification_stage="initial_chat")
    lead.conversation_history.append(SMSMessageSchema(sender="bot", text=body))
    lead.last_active_timestamp = datetime.now()
    await save_lead_to_db(lead)
    
    return jsonify({"status": "queued", "sid": message.sid}), 200

# Receive SMS endpoint

@app.route("/receive-sms", methods=["GET", "POST"])
async def receive_sms():
    try:
        from_number = request.form.get("From")  # You had "Form" — typo?
        to_number = request.form.get("To")
        body = request.form.get("Body")
    except Exception as e:
        raise Exception(e.__str__())

    # Debug log
    print(f"📩 Incoming SMS from {from_number}: {body}")
    lead = await get_lead_from_db(from_number)

    # Save to DB (assuming Message and db are correctly defined)
    # db_msg = Message(
    #     # sid=request.form.get('SmsSid', None),
    #     sid=None,
    #     from_number=from_number, 
    #     to_number=to_number, 
    #     body=body, 
    #     direction="inbound", 
    #     status="received", 
    # )
    # db.session.add(db_msg) 
    # db.session.commit() 
    # print("✅ Saved inbound SMS to DB.")

    print("✅====lead data from DB===", lead)
    if not lead:
        user_id = f"anon_{int(datetime.now().timestamp())}_{str(uuid.uuid4())[:8]}"
        lead = SMSLead(id=user_id, phone_number=from_number, qualification_stage="initial_chat")
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"user", "text":body }) )
        bot_message = "Hello! I'm Nia from The Paul Group. I'm here to help you with your final expense insurance questions. What would you like to know about our burial insurance coverage?"
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message}) )
        lead.last_active_timestamp = datetime.now()
        await save_lead_to_db(lead)
        print('\n=======Lead Saved to Db=====✅')

        # Return TwiML response
        resp = MessagingResponse()
        resp.message(bot_message)
        print('\n=======Bot Msg Prepared=====✅')
        return str(resp), 200, {'Content-Type': 'application/xml'}
    
    # If not a new lead, proceed to add user message and process
    lead.last_active_timestamp = datetime.now()
    lead.conversation_history.append(SMSMessageSchema().load({"sender":"user", "text":body}))
    faq_answer = await answer_from_uploaded_file(body)

    print('⚠=====faq_answer=====⚠',faq_answer)

    if faq_answer:
        lead.conversation_history.append(
            SMSMessageSchema().load({"sender":"bot", "text":faq_answer})
        )
        await save_lead_to_db(lead)
        # Return TwiML response
        resp = MessagingResponse()
        resp.message(faq_answer)
        return str(resp), 200, {'Content-Type': 'application/xml'}
        # return SmsChatResponse(
        #     bot_message          = faq_answer,
        #     lead_status          = lead.qualification_stage, 
        #     lead_data            = lead.model_dump(exclude_none=True),
        #     conversation_history = lead.conversation_history,
        #     user_id              = from_number  
        # )
    else: print('🚨=====FAQ and not found====🚨')

# Status callback endpoint
@app.route("/sms/status", methods=["POST"])
def status_callback():
    sid = request.form.get("MessageSid")
    status = request.form.get("MessageStatus")
    error_code = request.form.get("ErrorCode")

    msg = Message.query.filter_by(sid=sid).first()
    if msg:
        msg.status = status
        msg.error_code = error_code
        db.session.commit()
        print(f"📤 Updated message {sid} status: {status}")

    return ("", 204)

# View all messages
@app.route("/messages", methods=["GET"])
def get_all_messages():
    msgs = Message.query.order_by(Message.timestamp.desc()).all()
    data = []
    for m in msgs:
        data.append({
            "id": m.id,
            "sid": m.sid,
            "from_number": m.from_number,
            "to_number": m.to_number,
            "body": m.body,
            "direction": m.direction,
            "status": m.status,
            "error_code": m.error_code,
            "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    return jsonify(data), 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0",port=8000, debug=True)



# conversation flow   




# import os, json, uuid
# from datetime import datetime
# from dotenv import load_dotenv
# from flask import Flask, request, jsonify, url_for
# from flask_sqlalchemy import SQLAlchemy
# from twilio.rest import Client
# from twilio.twiml.messaging_response import MessagingResponse


# from sms_schemas import SMSLeadSchema, SMSMessageSchema as LeadMessage
# from sms_sqlite_utils import initialize_sqlite_db, save_lead_to_db, detect_recruiting_inquiry, generate_recruiting_response

# # --- Init ---
# load_dotenv()
# ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

# client = Client(ACCOUNT_SID, AUTH_TOKEN)
# app = Flask(__name__)
# app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sms.db")
# app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# db = SQLAlchemy(app)

# # DB model just for logging SMS messages
# class SMSLog(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     from_number = db.Column(db.String(32))
#     to_number = db.Column(db.String(32))
#     body = db.Column(db.Text)
#     direction = db.Column(db.String(10))
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# # --- Conversation Flow ---
# def run_conversation_flow(lead: Lead, user_message: str) -> str:
#     stage = lead.qualification_stage
#     msg_lower = user_message.lower().strip()
#     bot_message = ""

#     # Recruiting detection first
#     if stage in ["initial_chat", "recruiting_inquiry"] and detect_recruiting_inquiry(user_message):
#         lead.qualification_stage = "recruiting_inquiry"
#         bot_message = generate_recruiting_response(user_message)
#         return bot_message

#     if stage == "initial_chat":
#         lead.qualification_stage = "ask_name"
#         bot_message = "Great! To help us get started, could you please tell me your full name?"

#     elif stage == "ask_name":
#         lead.full_name = user_message.strip()
#         lead.qualification_stage = "ask_age"
#         first_name = lead.full_name.split()[0]
#         bot_message = f"Nice to meet you {first_name}! How old are you?"

#     elif stage == "ask_age":
#         if user_message.isdigit():
#             lead.age = int(user_message)
#             lead.qualification_stage = "ask_state"
#             bot_message = "Which state do you currently live in?"
#         else:
#             bot_message = "Please enter your age as a number."

#     elif stage == "ask_state":
#         lead.state_of_residence = user_message.strip()
#         lead.qualification_stage = "ask_health_confirm"
#         bot_message = "Do you have any existing health conditions? Reply Yes or No."

#     elif stage == "ask_health_confirm":
#         if "yes" in msg_lower:
#             lead.qualification_stage = "ask_health_details"
#             bot_message = "Please specify your health conditions."
#         elif "no" in msg_lower:
#             lead.general_health = "No"
#             lead.qualification_stage = "ask_budget"
#             bot_message = "What is your monthly budget range for coverage?"
#         else:
#             bot_message = "Please reply Yes or No."

#     elif stage == "ask_health_details":
#         lead.health_conditions = user_message.strip()
#         lead.qualification_stage = "ask_budget"
#         bot_message = "Thanks! What is your monthly budget range for coverage?"

#     elif stage == "ask_budget":
#         lead.budget_range = user_message.strip()
#         lead.qualification_stage = "ask_contact_time"
#         bot_message = "When is the best time for our agent to contact you?"

#     elif stage == "ask_contact_time":
#         lead.best_contact_time = user_message.strip()
#         lead.qualification_stage = "completed_qualification"
#         ticket_number = str(uuid.uuid4())[:8].upper()
#         lead.ticket_number = ticket_number
#         bot_message = f"✅ Thanks! Your qualification is complete. Ticket #{ticket_number}. An agent will reach out soon."

#     elif stage == "completed_qualification":
#         bot_message = "We already have your details ✅. An agent will reach out shortly."

#     else:
#         bot_message = "Sorry, I didn’t understand. Could you rephrase?"

#     return bot_message


# # --- Twilio webhook ---
# @app.route("/receive-sms", methods=["POST"])
# def receive_sms():
#     from_number = request.form.get("From")
#     body = request.form.get("Body")

#     # Create new lead object or load existing from DB
#     lead = Lead(
#         id=from_number,
#         phone_number=from_number,
#         qualification_stage="initial_chat",
#         conversation_history=[]
#     )

#     # Run conversation flow
#     bot_message = run_conversation_flow(lead, body)

#     # Append conversation
#     lead.conversation_history.append(
#         LeadMessage(sender="user", text=body, timestamp=datetime.utcnow())
#     )
#     lead.conversation_history.append(
#         LeadMessage(sender="bot", text=bot_message, timestamp=datetime.utcnow())
#     )

#     # Save to DB
#     save_lead_to_db(lead)

#     # Respond to Twilio
#     resp = MessagingResponse()
#     resp.message(bot_message)
#     return str(resp), 200, {'Content-Type': 'application/xml'}


# if __name__ == "__main__":
#     with app.app_context():
#         db.create_all()
#     initialize_sqlite_db()
#     app.run(host="0.0.0.0", port=8001, debug=True)









# from flask import Flask, request, jsonify, url_for
# from twilio.twiml.messaging_response import MessagingResponse
# from datetime import datetime
# import os
# import asyncio
# from sms_sqlite_utils import (
#     initialize_sms_sqlite_db,
#     save_lead_to_db,
#     get_lead_from_db,
#     SMSLead,
#     SMSMessage,
#     detect_recruiting_inquiry,
#     generate_recruiting_response,
#     LEAD_QUALIFICATION_STAGES
# )
# import uuid

# app = Flask(__name__)

# # --- Initialize DB ---
# initialize_sms_sqlite_db()

# # --- Twilio Credentials ---
# ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

# if not (ACCOUNT_SID and AUTH_TOKEN and TWILIO_NUMBER):
#     raise RuntimeError(
#         "Missing Twilio credentials: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_NUMBER "
#     )

# # Helper to run async coroutines
# def run_async(coro):
#     return asyncio.run(coro)

# # ---------------- Conversation Flow ----------------
# def run_conversation_flow(lead: SMSLead, user_message: str) -> str:
#     stage = lead.qualification_stage
#     msg_lower = user_message.lower().strip()
#     bot_message = ""

#     # Recruiting detection
#     if stage in ["initial_chat", "recruiting_inquiry"] and detect_recruiting_inquiry(user_message):
#         lead.qualification_stage = "recruiting_inquiry"
#         return generate_recruiting_response(user_message)

#     if stage == "initial_chat":
#         lead.qualification_stage = "ask_name"
#         bot_message = "Great! To help us get started, could you please tell me your full name?"

#     elif stage == "ask_name":
#         lead.full_name = user_message.strip()
#         lead.qualification_stage = "ask_age"
#         first_name = lead.full_name.split()[0]
#         bot_message = f"Nice to meet you {first_name}! How old are you?"

#     elif stage == "ask_age":
#         if user_message.isdigit():
#             lead.age = int(user_message)
#             lead.qualification_stage = "ask_state"
#             bot_message = "Which state do you currently live in?"
#         else:
#             bot_message = "Please enter your age as a number."

#     elif stage == "ask_state":
#         lead.state_of_residence = user_message.strip()
#         lead.qualification_stage = "ask_health_confirm"
#         bot_message = "Do you have any existing health conditions? Reply Yes or No."

#     elif stage == "ask_health_confirm":
#         if "yes" in msg_lower:
#             lead.qualification_stage = "ask_health_details"
#             bot_message = "Please specify your health conditions."
#         elif "no" in msg_lower:
#             lead.general_health = "No"
#             lead.qualification_stage = "ask_budget"
#             bot_message = "What is your monthly budget range for coverage?"
#         else:
#             bot_message = "Please reply Yes or No."

#     elif stage == "ask_health_details":
#         lead.health_conditions = user_message.strip()
#         lead.qualification_stage = "ask_budget"
#         bot_message = "Thanks! What is your monthly budget range for coverage?"

#     elif stage == "ask_budget":
#         lead.budget_range = user_message.strip()
#         lead.qualification_stage = "ask_contact_time"
#         bot_message = "When is the best time for our agent to contact you?"

#     elif stage == "ask_contact_time":
#         lead.best_contact_time = user_message.strip()
#         lead.qualification_stage = "completed_qualification"
#         ticket_number = str(uuid.uuid4())[:8].upper()
#         lead.ticket_number = ticket_number
#         bot_message = f"✅ Thanks! Your qualification is complete. Ticket #{ticket_number}. An agent will reach out soon."

#     elif stage == "completed_qualification":
#         bot_message = "We already have your details ✅. An agent will reach out shortly."

#     else:
#         bot_message = "Sorry, I didn’t understand. Could you rephrase?"

#     return bot_message

# # ---------------- Twilio Webhook ----------------
# @app.route("/receive-sms", methods=["POST"])
# def receive_sms():
#     from_number = request.form.get("From")
#     body = request.form.get("Body") or request.form.get("SmsBody")

#     # Load or create lead
#     lead = get_lead_from_db(from_number)
#     if not lead:
#         lead = SMSLead(id=from_number, phone_number=from_number)

#     # Append user message
#     lead.conversation_history.append(SMSMessage(sender="user", text=body, timestamp=datetime.utcnow()))

#     # Run conversation flow
#     bot_message = run_conversation_flow(lead, body)

#     # Append bot message
#     lead.conversation_history.append(SMSMessage(sender="bot", text=bot_message, timestamp=datetime.utcnow()))

#     # Update last active
#     lead.last_active_timestamp = datetime.utcnow()

#     # Save/update in DB
#     save_lead_to_db(lead)

#     # Respond to Twilio
#     resp = MessagingResponse()
#     resp.message(bot_message)
#     return str(resp), 200, {'Content-Type': 'application/xml'}

# # ---------------- Send SMS Endpoint ----------------
# @app.route("/send-sms", methods=["POST"])
# def send_sms():
#     from twilio.rest import Client
#     client = Client(ACCOUNT_SID, AUTH_TOKEN)
#     data = request.get_json(force=True)
#     to = data.get("to")
#     body = data.get("message")

#     if not to or not body:
#         return jsonify({"error": "missing 'to' or 'message'"}), 400

#     # Get or create lead
#     lead = get_lead_from_db(to)
#     if not lead:
#         lead = SMSLead(id=to, phone_number=to)

#     lead.conversation_history.append(SMSMessage(sender="bot", text=body, timestamp=datetime.utcnow()))

#     try:
#         status_cb = url_for("receive_sms", _external=True)
#         message = client.messages.create(
#             body=body,
#             from_=TWILIO_NUMBER,
#             to=to,
#             status_callback=status_cb
#         )

#         save_lead_to_db(lead)
#         return jsonify({
#             "status": "queued",
#             "sid": message.sid,
#             "lead_id": lead.id,
#             "conversation_history_length": len(lead.conversation_history)
#         }), 200

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == "__main__":
#     app.run(debug=True, port=5000)

