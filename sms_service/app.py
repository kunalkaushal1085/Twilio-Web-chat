import os
import re
import uuid
import asyncio
import traceback
from typing import List
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, url_for
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client
from openai import AsyncOpenAI, APIError
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

from file_embaded import answer_from_uploaded_file
from sms_schemas import SMSLead, SMSMessageSchema
from sms_sqlite_utils import (
    get_lead_from_db, save_lead_to_db, 
    detect_recruiting_inquiry, generate_recruiting_response,
    ensure_admin_table, ensure_welcome_table,
    initialize_sms_sqlite_db, handle_licensing_status_response,
    save_appointment_to_db_from_lead,ensure_appointment_table
)
from sms_helper import (
    get_available_time_slots, parse_slot_selection, parse_budget_amount
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
print(">>>>>BASE_DIR>>>>>>>",PROJECT_ROOT)
env_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(env_path)

print(f"✅ Loaded .env from: {env_path}")


#Load local .env only if present (safe for dev)
# load_dotenv('../.env')

# ╭──────────── Twilio and OpenAI credentials (from Render ENV or .env locally) ────────────╮
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-3.5-turbo" 

print("ACCOUNT_SID",ACCOUNT_SID)
print("AUTH_TOKEN",AUTH_TOKEN)
print("TWILIO_NUMBER",TWILIO_NUMBER)
if not (ACCOUNT_SID and AUTH_TOKEN and TWILIO_NUMBER):
    raise RuntimeError(
        "Missing Twilio credentials: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_NUMBER "
        "either in a .env (local) or Render Environment Variables (production)"
    )


# ╭──────────── Initialize OpenAI client ────────────╮
openai_client =None
if OPENAI_API_KEY:
    try:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        print("OpenAI client initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize OpenAI client. Please check your API key, network, and firewall settings: {e}")
else:
    print("WARNING: OpenAI client not initialized because OPENAI_API_KEY is missing. AI functionality will be limited.")


# ╭──────────── All Required Variables ────────────╮
AGENT_NAME = os.getenv("AGENT_NAME", "The Paul Group AI")
GENERAL_CHAT_SYSTEM_PROMPT = f"""
    You are {AGENT_NAME}, an AI assistant for The Paul Group, specializing in final expense insurance.
    Your primary goal is to provide helpful, informative, and engaging responses to user questions related to final expense insurance.
    Keep your responses concise and directly answer the user's question.

    After providing a satisfactory answer to a general query about final expense insurance (e.g., policy types, benefits, who needs it), you should subtly prompt the user to see if they are ready for a personalized quote or more specific information. For example, you could say something like: "Would you like to explore options to see what might fit your needs?" or "If you're interested in a personalized quote, I can help gather some details." Do NOT ask for specific personal details like name or age directly in this phase.
"""

# These are the questions the bot will ask based on the qualification stage
QUALIFICATION_QUESTIONS = {
    "ask_name": "Great! To help us get started, could you please tell me your **full name**?",
    "ask_age": "Thanks, [USER_NAME]! What is your **current age**?",
    "ask_state": "And what **state** do you currently reside in?",
    "ask_health_confirm": "Regarding your **general health**,Excellent! Do you have any major health conditions? (Yes/No) This helps us determine your eligibility?",
    "ask_health_details": "Could you briefly mention some of the **major health conditions** you have, so we can assess the best options?",
    "ask_budget": "What's your **monthly budget** for premiums? Please let me know how much you're comfortable spending per month (e.g., '$55', '$75', 'around $100').",
    "ask_contact_time": "Finally, what's the **best time** for a licensed agent to contact you? (e.g., 'morning', 'afternoon', 'evening', or specific days/times)",
    "ask_time_slot_confirmation": "Great! I have some available slots for {time_period}. Which specific time works best for you?\n\n{available_slots}\n\nPlease choose a number (1, 2, 3, etc.) or tell me which time you prefer.",
    "confirm_booking": "Perfect! I'll book you for **{selected_slot}**. Can I confirm this appointment time for you? (Yes/No)",
    "completed_qualification": "Thank you for providing all the details! We're processing your request.",
}



client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Flask app and DB
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///sms.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


@app.before_request
def on_startup():
    ensure_admin_table()
    ensure_welcome_table()
    initialize_sms_sqlite_db()
    ensure_appointment_table()

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

    lead = SMSLead(id=message.sid, qualification_stage="initial_chat")
    lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":body}))
    lead.last_active_timestamp = datetime.now()
    await save_lead_to_db(lead)
    
    return jsonify({"status": "queued", "sid": message.sid}), 200

# Receive SMS endpoint

@app.route("/receive-sms", methods=["GET", "POST"])
async def receive_sms():
    try:
        from_number = request.form.get("From")
        user_message = request.form.get("Body").strip()

        # data = request.get_json()
        # from_number = data.get("From")
        # user_message = data.get("Body").strip()
    except Exception as e:
        raise Exception(e.__str__())

    # Debug log
    print('=====Incomming SMS Details=====',request.form,'\n')
    print(f"📩 Incoming SMS from {from_number}: {user_message}\n")
    lead = await get_lead_from_db(from_number)
    print("✅====lead data from DB===\n", lead)

    if not lead and (user_message is None or user_message == ''):
        return send_reply_to_user("Please send 'Hi' to start the conversation")

    # --- Initial Greeting Logic ---
    if not lead:
        user_id = f"anon_{int(datetime.now().timestamp())}_{str(uuid.uuid4())[:8]}"
        lead = SMSLead(id=user_id, phone_number=from_number, qualification_stage="initial_chat")
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"user", "text":user_message }) )
        bot_message = "Hello! I'm Nia from The Paul Group. I'm here to help you with your final expense insurance questions. What would you like to know about our burial insurance coverage?"
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message}) )
        lead.last_active_timestamp = datetime.now()
        await save_lead_to_db(lead)
        print('\n=======Lead Saved to Db=====✅')

        return send_reply_to_user(bot_message)
    
    print('\n⚡=======User Qualification Stage======⚡',lead.qualification_stage,'\n')
    
    # If not a new lead, proceed to add user message and process
    lead.last_active_timestamp = datetime.now()
    lead.conversation_history.append(SMSMessageSchema().load({"sender":"user", "text":user_message}))
    faq_answer = await answer_from_uploaded_file(user_message)

    if faq_answer:
        lead.conversation_history.append(
            SMSMessageSchema().load({"sender":"bot", "text":faq_answer})
        )
        await save_lead_to_db(lead)
        return send_reply_to_user(faq_answer)

    
    # --- RECRUITING INQUIRY DETECTION ---
    if detect_recruiting_inquiry(user_message):
        print(f"DEBUG: Recruiting inquiry detected from user {user_id}: '{user_message}'")
        
        lead.qualification_stage = "recruiting_inquiry"
        bot_message = generate_recruiting_response(user_message)
        
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message}))
        await save_lead_to_db(lead)
        return send_reply_to_user(bot_message)
        # return ChatResponse(
        #     bot_message=bot_message,
        #     lead_status=lead.qualification_stage,
        #     lead_data=lead.model_dump(exclude_none=True),
        #     conversation_history=lead.conversation_history,
        #     user_id=user_id  # UPDATED: Include user_id
        # )
    
    # --- HANDLE RECRUITING FOLLOW-UP ---
    if lead.qualification_stage == "recruiting_inquiry":
        licensing_response = handle_licensing_status_response(user_message)
        
        if licensing_response != "Could you clarify if you currently have a life insurance license? This will help me connect you with the right person.":
            bot_message = licensing_response
            lead.qualification_stage = "recruiting_completed"
        else:
            bot_message = licensing_response
        
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message}))
        await save_lead_to_db(lead)
        return send_reply_to_user(bot_message)
        # return ChatResponse(
        #     bot_message=bot_message,
        #     lead_status=lead.qualification_stage,
        #     lead_data=lead.model_dump(exclude_none=True),
        #     conversation_history=lead.conversation_history,
        #     user_id=user_id  # UPDATED: Include user_id
        # )
    
    # --- HANDLE COMPLETED RECRUITING ---
    if lead.qualification_stage == "recruiting_completed":
        bot_message = "Thank you for your interest in joining The Paul Group! A recruiter will reach out to you soon. Is there anything else I can help you with today?"
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message}))
        await save_lead_to_db(lead)
        return send_reply_to_user(bot_message)
        # return ChatResponse(
        #     bot_message=bot_message,
        #     lead_status=lead.qualification_stage,
        #     lead_data=lead.model_dump(exclude_none=True),
        #     conversation_history=lead.conversation_history,
        #     user_id=user_id  # UPDATED: Include user_id
        # )

    # --- INSURANCE LEAD QUALIFICATION STATE MACHINE LOGIC ---
    if lead.qualification_stage == "initial_chat":
        if any(keyword in user_message.lower() for keyword in ["satisfied", "quote", "details", "yes", "start", "proceed", "sure"]):
            lead.qualification_stage = "ask_name"
            bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
            #previous working code else conditions
        # else:
        #     bot_message = await get_openai_response(lead.conversation_history, GENERAL_CHAT_SYSTEM_PROMPT)
        #     if "explore options" in bot_message.lower() or "personalized quote" in bot_message.lower():
        #         lead.qualification_stage = "ask_name"
        #         bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
        else:
            # NEW: Try to get answer from uploaded dataset first
            dataset_answer = await answer_from_uploaded_file(user_message)
            if dataset_answer:
                bot_message = dataset_answer.strip()
            else:
                # Fallback to OpenAI if no dataset match found
                bot_message = await get_openai_response(lead.conversation_history, GENERAL_CHAT_SYSTEM_PROMPT)
            
            # Check if we should transition to qualification
            if "explore options" in bot_message.lower() or "personalized quote" in bot_message.lower():
                lead.qualification_stage = "ask_name"
                bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
    elif lead.qualification_stage == "ask_name":
        if len(user_message.strip()) < 2 or any(char.isdigit() for char in user_message):
            bot_message = "Please provide your full name. We need it to personalize your quote. For example, 'John Doe'. (Names should not contain numbers or be too short.)"
            lead.conversation_history.pop()
        else:
            lead.full_name = user_message
            lead.qualification_stage = "ask_age"
            user_display_name = lead.full_name.split()[0] if lead.full_name else "there"
            bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage].replace("[USER_NAME]", user_display_name)
        
    elif lead.qualification_stage == "ask_age":
        try:
            age_match = re.search(r'\d+', user_message)
            if age_match:
                age = int(age_match.group())
                if 18 <= age <= 120:
                    lead.age = age
                    lead.qualification_stage = "ask_state"
                    bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
                else:
                    bot_message = "Please provide a realistic age between 18 and 120. What is your current age?"
            else:
                bot_message = "I couldn't find a valid age. Please provide your age as a number. For example, 'I am 65'."
            
            if "couldn't find a valid age" in bot_message or "Please provide a realistic age" in bot_message:
                lead.conversation_history.pop()
                await save_lead_to_db(lead)
                return send_reply_to_user(bot_message)
                # return ChatResponse(
                #     bot_message=bot_message,
                #     lead_status=lead.qualification_stage,
                #     lead_data=lead.model_dump(exclude_none=True),
                #     conversation_history=lead.conversation_history,
                #     user_id=user_id  # UPDATED: Include user_id
                # )
        except (ValueError, AttributeError):
            bot_message = "I couldn't understand your age. Please provide your age as a number. For example, 'I am 65'."
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return send_reply_to_user(bot_message)
            # return ChatResponse(
            #     bot_message=bot_message,
            #     lead_status=lead.qualification_stage,
            #     lead_data=lead.model_dump(exclude_none=True),
            #     conversation_history=lead.conversation_history,
            #     user_id=user_id  # UPDATED: Include user_id
            # )
            
    elif lead.qualification_stage == "ask_state":
        lead.state_of_residence = user_message
        lead.qualification_stage = "ask_health_confirm"
        bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
        
    elif lead.qualification_stage == "ask_health_confirm":
        user_health_response = user_message.lower()
        if "yes" in user_health_response and "no" not in user_health_response:
            lead.general_health = "Yes"
            lead.health_conditions = None
            lead.qualification_stage = "ask_budget"
            bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
        elif "no" in user_health_response and "yes" not in user_health_response:
            lead.general_health = "No"
            lead.qualification_stage = "ask_health_details"
            bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
        else:
            bot_message = "Please answer with 'Yes' or 'No' regarding major health conditions. (e.g., 'Yes', 'No, I have diabetes')"
            lead.conversation_history.pop() 
            await save_lead_to_db(lead)
            return send_reply_to_user(bot_message)
            # return ChatResponse(
            #     bot_message=bot_message,
            #     lead_status=lead.qualification_stage,
            #     lead_data=lead.model_dump(exclude_none=True),
            #     conversation_history=lead.conversation_history,
            #     user_id=user_id  # UPDATED: Include user_id
            # )
            
    elif lead.qualification_stage == "ask_health_details":
        lead.health_conditions = user_message
        lead.qualification_stage = "ask_budget"
        bot_message = QUALIFICATION_QUESTIONS[lead.qualification_stage]
        
    elif lead.qualification_stage == "ask_budget":
        is_valid, formatted_budget, amount = parse_budget_amount(user_message)
        
        if not is_valid:
            bot_message = "I couldn't understand your budget amount. Please tell me how much you'd like to spend per month. For example: '$55', '$75', or 'around $100'."
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return send_reply_to_user(bot_message)
            # return ChatResponse(
            #     bot_message=bot_message,
            #     lead_status=lead.qualification_stage,
            #     lead_data=lead.model_dump(exclude_none=True),
            #     conversation_history=lead.conversation_history,
            #     user_id=user_id
            # )
        lead.budget_range = formatted_budget
        lead.qualification_stage = "ask_contact_time"
        bot_message = f"Perfect! I've noted your budget as **{formatted_budget}**. {QUALIFICATION_QUESTIONS[lead.qualification_stage]}"
        
    elif lead.qualification_stage == "ask_contact_time":
        lead.best_contact_time = user_message
        
        # Generate available time slots using helper function
        time_period, slots = get_available_time_slots(user_message)
        lead.available_slots = slots
        
        # Create the slot selection message
        slots_text = '\n'.join(slots)
        bot_message = QUALIFICATION_QUESTIONS["ask_time_slot_confirmation"].format(
            time_period=time_period,
            available_slots=slots_text
        )
        
        lead.qualification_stage = "ask_time_slot_confirmation"

    elif lead.qualification_stage == "ask_time_slot_confirmation":
        print(f"DEBUG: Available slots: {lead.available_slots}")  # Add this line
        print(f"DEBUG: User input: '{user_message}'")
        is_valid, selected_slot = parse_slot_selection(user_message, lead.available_slots or [])
        print(f"DEBUG: Parse result - is_valid: {is_valid}, selected_slot: '{selected_slot}'")
        if not is_valid:
            available_slots_text = '\n'.join(lead.available_slots or [])
            bot_message = f"Please select one of the available time slots by choosing a number (1, 2, 3, 4) or mentioning the specific time:\n\n{available_slots_text}"
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return send_reply_to_user(bot_message)
            # return ChatResponse(
            #     bot_message=bot_message,
            #     lead_status=lead.qualification_stage,
            #     lead_data=lead.model_dump(exclude_none=True),
            #     conversation_history=lead.conversation_history,
            #     user_id=user_id
            # )
        
        lead.selected_time_slot = selected_slot
        lead.qualification_stage = "confirm_booking"
        bot_message = QUALIFICATION_QUESTIONS["confirm_booking"].format(selected_slot=selected_slot)

    elif lead.qualification_stage == "confirm_booking":
        user_confirmation = user_message.lower()
        if "yes" in user_confirmation and "no" not in user_confirmation:
            lead.qualification_stage = "completed_qualification"
            
            ticket_number = str(uuid.uuid4())[:8].upper()
            lead.ticket_number = ticket_number
            # Save booking date = today’s date + selected slot
            try:
                await save_appointment_to_db_from_lead(lead)
            except Exception as e:
                print(f"ERROR saving appointment: {e}")

            bot_message = f"{QUALIFICATION_QUESTIONS[lead.qualification_stage]} Your unique ticket number is **{ticket_number}** and your booking is confirmed for **{lead.selected_time_slot}**. We will contact you at the scheduled time!"
        #user confermations
        elif "no" in user_confirmation and "yes" not in user_confirmation:
            # Go back to slot selection
            lead.qualification_stage = "ask_time_slot_confirmation"
            available_slots_text = '\n'.join(lead.available_slots or [])
            bot_message = f"No problem! Please choose a different time slot:\n\n{available_slots_text}\n\nWhich time works better for you?"
        else:
            bot_message = "Please confirm with 'Yes' to book this time slot, or 'No' to choose a different time."
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return send_reply_to_user(bot_message)
            # return ChatResponse(
            #     bot_message=bot_message,
            #     lead_status=lead.qualification_stage,
            #     lead_data=lead.model_dump(exclude_none=True),
            #     conversation_history=lead.conversation_history,
            #     user_id=user_id
            # )
        
    elif lead.qualification_stage == "completed_qualification":
        bot_message = "You're welcome! We appreciate you providing your details. Our agent will be in touch shortly. Is there anything else I can help you with regarding final expense insurance today?"

    # Add the bot's response to the conversation history
    if "Please provide your full name." not in bot_message and \
       "couldn't find a valid age" not in bot_message and \
       "Please provide a realistic age" not in bot_message and \
       "I couldn't understand your age" not in bot_message and \
       "Please answer with 'Yes' or 'No'" not in bot_message and \
       "I couldn't understand your budget amount" not in bot_message and \
       "Please select one of the available time slots" not in bot_message and \
       "Please confirm with 'Yes'" not in bot_message:
        lead.conversation_history.append(SMSMessageSchema().load({"sender":"bot", "text":bot_message }))
    
    await save_lead_to_db(lead)
    return send_reply_to_user(bot_message)

    # return ChatResponse(
    #     bot_message=bot_message,
    #     lead_status=lead.qualification_stage,
    #     lead_data=lead.model_dump(exclude_none=True),
    #     conversation_history=lead.conversation_history,
    #     ticket_number=ticket_number,
    #     user_id=user_id  # Include user_id for frontend tracking
    # )



# Status callback endpoint
# @app.route("/sms/status", methods=["POST"])
# def status_callback():
#     sid = request.form.get("MessageSid")
#     status = request.form.get("MessageStatus")
#     error_code = request.form.get("ErrorCode")

#     msg = Message.query.filter_by(sid=sid).first()
#     if msg:
#         msg.status = status
#         msg.error_code = error_code
#         db.session.commit()
#         print(f"📤 Updated message {sid} status: {status}")

#     return ("", 204)

# View all messages
# @app.route("/messages", methods=["GET"])
# def get_all_messages():
#     msgs = Message.query.order_by(Message.timestamp.desc()).all()
#     data = []
#     for m in msgs:
#         data.append({
#             "id": m.id,
#             "sid": m.sid,
#             "from_number": m.from_number,
#             "to_number": m.to_number,
#             "body": m.body,
#             "direction": m.direction,
#             "status": m.status,
#             "error_code": m.error_code,
#             "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S")
#         })
#     return jsonify(data), 200




# ==================Helper Functions=================

# ---Send Reply to User----
def send_reply_to_user(msg:str):
    # Return TwiML response
    resp = MessagingResponse()
    resp.message(msg)
    print('\n=======Bot Msg Prepared=====✅', msg)
    return str(resp), 200, {'Content-Type': 'application/xml'}


# --- Helper Functions ---
async def get_openai_response(chat_history: List[SMSMessageSchema], system_prompt: str) -> str:
    """
    Calls the OpenAI API to get a response using the provided system prompt.
    Handles API-specific errors.
    """
    if openai_client is None:
        print("DEBUG: OpenAI client is not initialized, cannot get response for chat.")
        return "I cannot connect to my AI services at the moment. Please inform the administrator."

    messages_for_api = []
    messages_for_api.append({"role": "system", "content": system_prompt})
    
    for msg in chat_history:
        messages_for_api.append({
            "role": "user" if msg["sender"] == "user" else "assistant",
            "content": msg["text"]
        })
        
    try:
        # completion = await client.chat.completions.create(
        #     model=OPENAI_MODEL,
        #     messages=messages_for_api,
        #     temperature=0.7,
        #     max_tokens=500
        # )
        completion = await openai_client.chat.completions.create( # <--- This is correct
            model=OPENAI_MODEL,
            messages=messages_for_api,
            temperature=0.7,
            max_tokens=500
        )
        text = completion.choices[0].message.content
        print(f"DEBUG: Received response from OpenAI: '{text[:100]}...'")
        return text
    except APIError as e:
        print(f"ERROR: OpenAI API Call Failed! Status {e.status_code}, Message: {e.message}")
        if e.response:
            try:
                print(f"  Response Body: {e.response.text}")
            except Exception:
                print(f"  Response Body (non-text): {e.response}")
        return "I'm having trouble connecting to my AI right now. Please try again in a moment."
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during OpenAI API call: {e}")
        traceback.print_exc()
        return "An unexpected error occurred with the AI service. Please try again."



if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0",port=8000, debug=True)





