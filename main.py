from typing import List
from fastapi import FastAPI, HTTPException, status,UploadFile, File,Form,Header,Depends
import aiofiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session
from datetime import datetime
import os
import uuid 
import re
import shutil
import json 
from typing import List, Optional, Dict,Any
from helper import get_available_time_slots, parse_slot_selection, parse_budget_amount
from sms_service.file_embaded import answer_from_uploaded_file
import traceback
from dotenv import load_dotenv
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from fastapi import Form, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from sqlite_utils import (
    ensure_admin_table, get_admin_by_email,
    create_admin, update_admin_password
)
from auths import (
    hash_password, verify_password,
    create_access_token, decode_token
)

security = HTTPBearer()

# --- OpenAI Client Imports ---
from openai import AsyncOpenAI

# This MUST run BEFORE OpenAI() is called if your key is in .env
load_dotenv()

SECRET_KEY = "Mahjgdajjhsafjahfkjahfn"
ALGORITHM = "HS256"

EMBED_MODEL = "text-embedding-3-small" 
SIM_THRESHOLD = 0.85

# Import schemas and SQLite utilities

from schemas import Lead, Message, ChatRequest, ChatResponse, LeadQualificationStage
from sqlite_utils import (
    initialize_sqlite_db, get_lead_from_db, save_lead_to_db, get_all_leads_from_db,
    detect_recruiting_inquiry, generate_recruiting_response, handle_licensing_status_response,
    get_recruiting_leads_from_db,ensure_admin_table,store_uploaded_file_info,store_versioned_dataset, get_active_dataset_version, 
    get_all_dataset_versions, set_active_dataset_version,_get_latest_file_id,ensure_welcome_table,
    get_welcome_message,
    update_welcome_message,
    ensure_quicklink_table, get_active_quicklinks, create_quicklink,update_quicklink,ensure_theme_table,delete_quicklink,get_theme_config,update_theme_config,get_all_conversations_from_db,ensure_appointment_table,save_appointment_to_db_from_lead,get_appointments_from_db,get_appointment_by_id
)

# Initialize FastAPI app
app = FastAPI(title="The Paul Group Web Chatbot API (Lead Qualification + Recruiting)",
              description="FastAPI web chat API with multi-turn lead qualification for final expense insurance and recruiting detection.")

# Static folder for serving uploaded images
UPLOAD_FOLDER = "media"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.mount("/media", StaticFiles(directory=UPLOAD_FOLDER), name="media")

# Add CORS middleware for anonymous access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods including GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],  # Allows all headers
    expose_headers=["*"]
)

@app.on_event("startup")
def on_startup():
    ensure_admin_table()
    ensure_welcome_table()
    ensure_quicklink_table()
    ensure_theme_table()
    ensure_appointment_table()

# --- LLM Configuration ---
AGENT_NAME = os.getenv("AGENT_NAME", "The Paul Group AI")

# Get the API key from environment variables (set by load_dotenv if from .env file)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 
# client = AsyncOpenAI(api_key=OPENAI_API_KEY)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = "gpt-3.5-turbo" 
# Check if the key is available before initializing the client
if not OPENAI_API_KEY:
    print("CRITICAL ERROR: OPENAI_API_KEY is not set. Please ensure it's in your .env file or system environment.")

# Choose your desired OpenAI model

# Initialize OpenAI client
# client = None # Initialize as None; it will be set if API key is found
openai_client =None
if OPENAI_API_KEY: # Only attempt to initialize if the API key is available
    try:
        # client = AsyncOpenAI() # Old incorrect initialization
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        print("OpenAI client initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize OpenAI client. Please check your API key, network, and firewall settings: {e}")
else:
    print("WARNING: OpenAI client not initialized because OPENAI_API_KEY is missing. AI functionality will be limited.")

# --- LLM Prompts ---
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

# --- Helper Functions ---
async def get_openai_response(chat_history: List[Message], system_prompt: str) -> str:
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
            "role": "user" if msg.sender == "user" else "assistant",
            "content": msg.text
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

# --- FastAPI Endpoints ---

@app.on_event("startup")
async def startup_event():
    """Initializes SQLite database on application startup."""
    print("FastAPI application starting up...")
    initialize_sqlite_db()
    print("FastAPI application started. SQLite DB initialized.")

@app.post("/chat", response_model=ChatResponse)
async def chat_with_bot(chat_request: ChatRequest):
    """
    Handles incoming chat messages for anonymous users and implements 
    the lead qualification state machine with recruiting detection.
    """
    # UPDATED: Auto-generate user_id if not provided (for anonymous users)
    user_id = chat_request.user_id or f"anon_{int(datetime.now().timestamp())}_{str(uuid.uuid4())[:8]}"
    # user_message = chat_request.message.strip()
    user_message = chat_request.message
    print(user_message,'usermessage')

    lead = await get_lead_from_db(user_id)
    
    bot_message = ""
    ticket_number = None
    
    # --- Initial Greeting Logic ---
    if not lead:
        lead = Lead(id=user_id, qualification_stage="initial_chat")
        # Save user's first message in conversation history
        lead.conversation_history.append(Message(sender="user", text=user_message))
        # bot_message = "Hello! I'm Nia from The Paul Group. I'm here to help you with your final expense insurance questions. What would you like to know about our burial insurance coverage?"
        bot_message = ""
        lead.conversation_history.append(Message(sender="bot", text=bot_message))
        lead.last_active_timestamp = datetime.now()
        await save_lead_to_db(lead)
        
        # UPDATED: Return the initial greeting with the generated user_id
        return ChatResponse(
            bot_message=bot_message,
            lead_status=lead.qualification_stage,
            lead_data=lead.model_dump(exclude_none=True),
            conversation_history=lead.conversation_history,
            user_id=user_id  # Include the generated user_id in response
        )
    
    # If not a new lead, proceed to add user message and process
    lead.last_active_timestamp = datetime.now()
    lead.conversation_history.append(Message(sender="user", text=user_message))
    faq_answer = await answer_from_uploaded_file(user_message)
# ____________-___________________________________________
    if faq_answer:
        lead.conversation_history.append(
            Message(sender="bot", text=faq_answer)
        )
        await save_lead_to_db(lead)
        return ChatResponse(
            bot_message          = faq_answer,
            lead_status          = lead.qualification_stage, 
            lead_data            = lead.model_dump(exclude_none=True),
            conversation_history = lead.conversation_history,
            user_id              = user_id  
        )



    # --- RECRUITING INQUIRY DETECTION ---
    if detect_recruiting_inquiry(user_message):
        print(f"DEBUG: Recruiting inquiry detected from user {user_id}: '{user_message}'")
        
        lead.qualification_stage = "recruiting_inquiry"
        bot_message = generate_recruiting_response(user_message)
        
        lead.conversation_history.append(Message(sender="bot", text=bot_message))
        await save_lead_to_db(lead)
        
        return ChatResponse(
            bot_message=bot_message,
            lead_status=lead.qualification_stage,
            lead_data=lead.model_dump(exclude_none=True),
            conversation_history=lead.conversation_history,
            user_id=user_id  # UPDATED: Include user_id
        )
    
    # --- HANDLE RECRUITING FOLLOW-UP ---
    if lead.qualification_stage == "recruiting_inquiry":
        licensing_response = handle_licensing_status_response(user_message)
        
        if licensing_response != "Could you clarify if you currently have a life insurance license? This will help me connect you with the right person.":
            bot_message = licensing_response
            lead.qualification_stage = "recruiting_completed"
        else:
            bot_message = licensing_response
        
        lead.conversation_history.append(Message(sender="bot", text=bot_message))
        await save_lead_to_db(lead)
        return ChatResponse(
            bot_message=bot_message,
            lead_status=lead.qualification_stage,
            lead_data=lead.model_dump(exclude_none=True),
            conversation_history=lead.conversation_history,
            user_id=user_id  # UPDATED: Include user_id
        )
    
    # --- HANDLE COMPLETED RECRUITING ---
    if lead.qualification_stage == "recruiting_completed":
        bot_message = "Thank you for your interest in joining The Paul Group! A recruiter will reach out to you soon. Is there anything else I can help you with today?"
        lead.conversation_history.append(Message(sender="bot", text=bot_message))
        await save_lead_to_db(lead)
        
        return ChatResponse(
            bot_message=bot_message,
            lead_status=lead.qualification_stage,
            lead_data=lead.model_dump(exclude_none=True),
            conversation_history=lead.conversation_history,
            user_id=user_id  # UPDATED: Include user_id
        )

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
                return ChatResponse(
                    bot_message=bot_message,
                    lead_status=lead.qualification_stage,
                    lead_data=lead.model_dump(exclude_none=True),
                    conversation_history=lead.conversation_history,
                    user_id=user_id  # UPDATED: Include user_id
                )
        except (ValueError, AttributeError):
            bot_message = "I couldn't understand your age. Please provide your age as a number. For example, 'I am 65'."
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return ChatResponse(
                bot_message=bot_message,
                lead_status=lead.qualification_stage,
                lead_data=lead.model_dump(exclude_none=True),
                conversation_history=lead.conversation_history,
                user_id=user_id  # UPDATED: Include user_id
            )
            
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
            return ChatResponse(
                bot_message=bot_message,
                lead_status=lead.qualification_stage,
                lead_data=lead.model_dump(exclude_none=True),
                conversation_history=lead.conversation_history,
                user_id=user_id  # UPDATED: Include user_id
            )
            
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
            return ChatResponse(
                bot_message=bot_message,
                lead_status=lead.qualification_stage,
                lead_data=lead.model_dump(exclude_none=True),
                conversation_history=lead.conversation_history,
                user_id=user_id
            )
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
            return ChatResponse(
                bot_message=bot_message,
                lead_status=lead.qualification_stage,
                lead_data=lead.model_dump(exclude_none=True),
                conversation_history=lead.conversation_history,
                user_id=user_id
            )
        
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
                _appt_id = save_appointment_to_db_from_lead(lead)
            except Exception as e:
                print(f"ERROR saving appointment: {e}")

            bot_message = f"{QUALIFICATION_QUESTIONS[lead.qualification_stage]} Your unique ticket number is **{ticket_number}** and your booking is confirmed for **{lead.selected_time_slot}**. We will contact you at the scheduled time!"
            
        elif "no" in user_confirmation and "yes" not in user_confirmation:
            # Go back to slot selection
            lead.qualification_stage = "ask_time_slot_confirmation"
            available_slots_text = '\n'.join(lead.available_slots or [])
            bot_message = f"No problem! Please choose a different time slot:\n\n{available_slots_text}\n\nWhich time works better for you?"
        else:
            bot_message = "Please confirm with 'Yes' to book this time slot, or 'No' to choose a different time."
            lead.conversation_history.pop()
            await save_lead_to_db(lead)
            return ChatResponse(
                bot_message=bot_message,
                lead_status=lead.qualification_stage,
                lead_data=lead.model_dump(exclude_none=True),
                conversation_history=lead.conversation_history,
                user_id=user_id
            )
        
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
        lead.conversation_history.append(Message(sender="bot", text=bot_message))
    
    await save_lead_to_db(lead)

    # UPDATED: Always return user_id in the response
    return ChatResponse(
        bot_message=bot_message,
        lead_status=lead.qualification_stage,
        lead_data=lead.model_dump(exclude_none=True),
        conversation_history=lead.conversation_history,
        ticket_number=ticket_number,
        user_id=user_id  # Include user_id for frontend tracking
    )

# --- Admin Endpoints (for viewing stored data) ---

@app.get("/admin/leads/{user_id}", response_model=Lead)
async def get_lead_data(user_id: str):
    """Admin endpoint to view a specific lead's data and chat history."""
    lead = await get_lead_from_db(user_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead.model_dump(mode="json")

@app.get("/admin/all_leads", response_model=List[Lead])
async def get_all_leads_admin_view():
    """Admin endpoint to view all leads in the database."""
    leads = await get_all_leads_from_db()
    return [lead.model_dump(mode="json") for lead in leads]

@app.get("/admin/recruiting_leads", response_model=List[Lead])
async def get_recruiting_leads_admin_view():
    """Admin endpoint to view all recruiting inquiry leads in the database."""
    recruiting_leads = await get_recruiting_leads_from_db()
    return [lead.model_dump(mode="json") for lead in recruiting_leads]


CHUNK_SIZE = 1000  
DATASET_DIR = "Webchat_dataset"

# @app.post("/upload-dataset/")
# async def upload_dataset(file: UploadFile = File(...)):
#     os.makedirs(DATASET_DIR, exist_ok=True)
    
#     # Save uploaded file temporarily
#     filepath = f"{DATASET_DIR}/{file.filename}"
#     async with aiofiles.open(filepath, 'wb') as out_file:
#         content = await file.read()
#         await out_file.write(content)
    
#     # Read JSON and process in chunks
#     async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
#         content = await f.read()
#         data = json.loads(content)

#     chunk_files = []
#     for i in range(0, len(data), CHUNK_SIZE):
#         chunk = data[i:i+CHUNK_SIZE]
#         chunk_file_path = f"{DATASET_DIR}/chunk_{i//CHUNK_SIZE + 1}.jsonl"
        
#         async with aiofiles.open(chunk_file_path, "w", encoding="utf-8") as out:
#             for record in chunk:
#                 prompt = record["user_input"]
#                 completion = " " + record["bot_response"]
#                 await out.write(json.dumps({"prompt": prompt, "completion": completion}) + "\n")
        
#         chunk_files.append(chunk_file_path)
    
#     # Upload each chunk to OpenAI asynchronously
#     uploaded_files = []
#     for chunk_path in chunk_files:
#         async with aiofiles.open(chunk_path, "rb") as f:
#             # aiofiles doesn't support reading as binary directly for AsyncOpenAI
#             # so read the entire file into memory
#             file_data = await f.read()

#         response = await client.files.create(file=(os.path.basename(chunk_path), file_data), purpose='fine-tune')
#         uploaded_files.append(response.id)
#     for file_id in uploaded_files:
#         store_uploaded_file_info(file_id=file_id, chunks_created=len(chunk_files))
#     return {
#         "status": "success",
#         "uploaded_files": uploaded_files,
#         "chunks_created": len(chunk_files)
#     }


#admin login functionality
def get_current_admin(
    cred: HTTPAuthorizationCredentials = Security(security)
):
    payload = decode_token(cred.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    admin = get_admin_by_email(payload["sub"])
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin

#same api change the algo and urlname
@app.post("/upload-dataset-version/")
async def upload_dataset_version(
    file: UploadFile = File(...),
    version_label: str = Form(...),
    description: str = Form(""),
    admin: dict = Depends(get_current_admin)  # Requires admin login
):
    """Upload a versioned dataset with label and description."""
    try:
        # ✅ Validate file extension (only .json allowed)
        if not file.filename.lower().endswith(".json"):
            return {
                "status": "error",
                "message": "Invalid file type. Only JSON files are allowed."
            }

        # ✅ Check if version already exists
        versions = get_all_dataset_versions()
        if any(v["version"] == version_label for v in versions):
            return {
                "status": "error",
                "message": f"Version {version_label} already exists."
            }

        os.makedirs(DATASET_DIR, exist_ok=True)

        # Save uploaded file temporarily
        filepath = f"{DATASET_DIR}/{file.filename}"
        async with aiofiles.open(filepath, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)

        # ✅ Read & validate JSON file
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
        except json.JSONDecodeError:
            os.remove(filepath)  # cleanup
            return {
                "status": "error",
                "message": "Uploaded file is not a valid JSON."
            }

        total_records = len(data)
        chunk_files = []

        # ✅ Split into chunks
        for i in range(0, len(data), CHUNK_SIZE):
            chunk = data[i:i+CHUNK_SIZE]
            chunk_file_path = f"{DATASET_DIR}/{version_label}_chunk_{i//CHUNK_SIZE + 1}.jsonl"

            async with aiofiles.open(chunk_file_path, "w", encoding="utf-8") as out:
                for record in chunk:
                    prompt = record.get("user_input", "")
                    completion = " " + record.get("bot_response", "")
                    await out.write(json.dumps({"prompt": prompt, "completion": completion}) + "\n")

            chunk_files.append(chunk_file_path)

        # ✅ Upload each chunk to OpenAI
        uploaded_files = []
        for chunk_path in chunk_files:
            async with aiofiles.open(chunk_path, "rb") as f:
                file_data = await f.read()

            response = await client.files.create(
                file=(os.path.basename(chunk_path), file_data),
                purpose='fine-tune'
            )
            uploaded_files.append(response.id)

        # ✅ Store versioned dataset
        store_versioned_dataset(
            version_label=version_label,
            description=description,
            file_ids=uploaded_files,
            total_records=total_records,
            created_by=admin["email"]
        )

        # ✅ Clean up temp files
        for chunk_path in chunk_files:
            os.remove(chunk_path)
        os.remove(filepath)

        return {
            "status": "success",
            "version": version_label,
            "description": description,
            "total_records": total_records,
            "uploaded_files": uploaded_files,
            "chunks_created": len(chunk_files),
            "message": f"Dataset version {version_label} uploaded and activated"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"An unexpected error occurred: {str(e)}"
        }

@app.get("/dataset-versions/")
async def list_dataset_versions():
    """List all dataset versions (no auth required for viewing)."""
    versions = get_all_dataset_versions()
    active_version = get_active_dataset_version()
    
    return {
        "versions": versions,
        "active_version": active_version["version"] if active_version else None,
        "total_versions": len(versions)
    }


@app.post("/switch-dataset-version/")
async def switch_dataset_version(
    version_label: str = Form(...),
    admin: dict = Depends(get_current_admin)  # Requires admin login
):
    """Switch to a different dataset version."""
    
    if not set_active_dataset_version(version_label):
        raise HTTPException(status_code=404, detail=f"Version {version_label} not found")
    
    active_version = get_active_dataset_version()
    
    return {
        "status": "success",
        "message": f"Switched to dataset version {version_label}",
        "active_version": active_version
    }


@app.get("/active-dataset-version/")
async def get_current_active_version():
    """Get currently active dataset version info."""
    active = get_active_dataset_version()
    
    if not active:
        # Fallback to old system
        file_id = _get_latest_file_id()  # Your existing function
        if file_id:
            return {
                "version": "legacy",
                "file_ids": [file_id],
                "total_records": "unknown",
                "message": "Using legacy dataset (no version info)"
            }
        else:
            return {"message": "No dataset found"}
    
    return active


@app.post("/register")
def register_admin(
    email: str = Form(...),
    password: str = Form(...)
):
    ensure_admin_table()
    if get_admin_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered")

    admin = create_admin(email, hash_password(password))
    return {"id": admin["id"], "email": admin["email"], "message": "Admin registered"}


@app.post("/login")
def login_admin(
    email: str = Form(...),
    password: str = Form(...)
):
    admin = get_admin_by_email(email)
    if not admin or not verify_password(password, admin["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": admin["email"]})
    token = create_access_token({"sub": admin["email"]}, minutes=120)
    return {"access_token": token, "token_type": "bearer", "message": "Admin login successfully"}


@app.post("/update-password")
def update_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    if not verify_password(old_password, admin["password"]):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    update_admin_password(admin["id"], hash_password(new_password))
    return {"message": "Password updated successfully"}


@app.get("/get-welcome-message")
def read_welcome_message():
    return {"message": get_welcome_message()}
 
 
@app.post("/welcome-message")
def write_welcome_message(
    message: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    update_welcome_message(message)
    return {"message": "Welcome message updated successfully"}



@app.get("/quick-links")
def read_quick_links():
    return {"quick_links": get_active_quicklinks()}
 
 
@app.post("/quick-links")
def add_quick_link(
    title: str = Form(...),
    description: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    if not title.strip() or not description.strip():
        raise HTTPException(status_code=400, detail="Title and description are required")
   
    create_quicklink(title, description)
    return {"message": "Quick link created"}
 
@app.put("/quick-links/{link_id}")
def edit_quick_link(
    link_id: int,
    title: str = Form(...),
    description: str = Form(...),
    admin: dict = Depends(get_current_admin)
):
    if not title.strip() or not description.strip():
        raise HTTPException(status_code=400, detail="Title and description are required")
 
    success = update_quicklink(link_id, title, description)
    if not success:
        raise HTTPException(status_code=404, detail="Quick link not found")
 
    return {"message": "Quick link updated successfully"}
 
@app.delete("/quick-links/{link_id}")
def delete_quick_link(
    link_id: int,
    admin: dict = Depends(get_current_admin)
):
    success = delete_quicklink(link_id)
    if not success:
        raise HTTPException(status_code=404, detail="Quick link not found")
 
    return {"message": "Quick link deleted successfully"}


@app.get("/theme-config")
def read_theme_config():
    try:
        return {"status":"sucess","theme": get_theme_config()}
    except Exception as e:
        return {"status":"failed","message":str(e)}

from starlette.requests import Request
def get_base_url(request: Request):
    return str(request.base_url).rstrip("/")

MEDIA_DIR = os.path.join(os.getcwd(), "media")
LOGO_DIR = os.path.join(os.getcwd(), "logo")
@app.post("/theme-config")
async def write_theme_config(
    request: Request,
    primary_color: str = Form(None),
    background_color: str = Form(None),
    text_color: str = Form(None),
    border_radius: int = Form(None),
    widget_position: str = Form(None),
    welcome_delay: int = Form(None),
    company_name: str = Form(None),
    avatar_image: UploadFile = File(None),
    body_font_family: str = Form(None),
    body_font_size: int = Form(None),
    body_font_weight: str = Form(None),
    heading_font_family: str = Form(None),
    heading_font_weight: str = Form(None),
    logo: UploadFile = File(None),
    admin: dict = Depends(get_current_admin)
):
    # Get existing config so we can keep values if not provided
    existing_config = get_theme_config()

    # Handle file upload
    avatar_image_url = existing_config.get("avatar_image_url")
    if avatar_image:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        file_path = os.path.join(MEDIA_DIR, avatar_image.filename)
        with open(file_path, "wb") as f:
            f.write(await avatar_image.read())
        # Build URL dynamically based on request
        base_url = get_base_url(request)
        avatar_image_url = f"{base_url}/media/{avatar_image.filename}"
    # Handle logo image upload
    logo_url = existing_config.get("logo")
    if logo:
        os.makedirs(LOGO_DIR, exist_ok=True)
        file_path = os.path.join(LOGO_DIR, logo.filename)
        with open(file_path, "wb") as f:
            f.write(await logo.read())
        base_url = get_base_url(request)
        logo_url = f"{base_url}/logo/{logo.filename}"
    data = {
        "primary_color": primary_color.strip() if primary_color else existing_config.get("primary_color"),
        "background_color": background_color.strip() if background_color else existing_config.get("background_color"),
        "text_color": text_color.strip() if text_color else existing_config.get("text_color"),
        "border_radius": border_radius if border_radius is not None else existing_config.get("border_radius"),
        "widget_position": widget_position.strip() if widget_position else existing_config.get("widget_position"),
        "avatar_image_url": avatar_image_url,
        "welcome_delay": welcome_delay if welcome_delay is not None else existing_config.get("welcome_delay"),
        "company_name": company_name.strip() if company_name else existing_config.get("company_name"),
        "logo": logo_url,
        "body_font_family": body_font_family.strip() if body_font_family else existing_config.get("body_font_family"),
        "body_font_size": body_font_size if body_font_size is not None else existing_config.get("body_font_size"),
        "body_font_weight": body_font_weight.strip() if body_font_weight else existing_config.get("body_font_weight"),
        "heading_font_family": heading_font_family.strip() if heading_font_family else existing_config.get("heading_font_family"),
        "heading_font_weight": heading_font_weight.strip() if heading_font_weight else existing_config.get("heading_font_weight")
    }

    update_theme_config(data)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Theme configuration saved",
            "avatar_image_url": avatar_image_url,
            "logo_url": logo_url
        }
    )


@app.get("/conversations", response_model=List[dict])
async def get_conversations():
    """
    Returns all conversations from the leads table.
    """
    try:
        conversations = await get_all_conversations_from_db()
        return conversations
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/conversations/{conversation_id}", response_model=dict)
async def get_conversation(conversation_id: str):
    """
    Returns a single conversation for the given conversation_id (lead.id).
    """
    try:
        leads = await get_all_leads_from_db()

        # find the matching lead
        for lead in leads:
            if str(lead.id) == str(conversation_id):
                return {
                    "id": lead.id,
                    "conversation_history": lead.conversation_history
                }

        # If not found
        return JSONResponse(status_code=404, content={"error": "Conversation not found"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/appointments")
def list_appointments(lead_id: Optional[str] = None):
    """
    Read appointments (all or by lead_id).
    """
    try:
        # return {"appointments": get_appointments_from_db(lead_id)}
        appointments = get_appointments_from_db(lead_id)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Appointments fetched successfully",
                "count": len(appointments),
                "appointments": appointments
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
 
@app.get("/appointments/{appointment_id}")
def read_appointment(appointment_id: int):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from fastapi.responses import JSONResponse, PlainTextResponse
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not (ACCOUNT_SID and AUTH_TOKEN and TWILIO_NUMBER):
    raise RuntimeError(
        "Missing Twilio credentials: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_NUMBER"
    )

client = Client(ACCOUNT_SID, AUTH_TOKEN)
# class SendSMSRequest(BaseModel):
#     to: str
#     message: str

# @app.post("/send-sms")
# async def send_sms(request_data: SendSMSRequest):
#     to = request_data.to
#     body = request_data.message

#     if not to or not body:
#         raise HTTPException(status_code=400, detail="Missing 'to' or 'message'")

#     # Status callback URL (replace with your actual endpoint if needed)
#     status_cb = " https://1e5911f44a22.ngrok-free.app/status-callback"

#     message = client.messages.create(
#         body=body,
#         from_=TWILIO_NUMBER,
#         to=to,
#         status_callback=status_cb
#     )

#     # Save outbound message to DB
#     db_msg = Message(
#         sid=message.sid,
#         from_number=TWILIO_NUMBER,
#         to_number=to,
#         body=body,
#         direction="outbound",
#         status=message.status,
#     )

#     with db.session.begin():  # ensures commit/rollback
#         db.session.add(db_msg)

#     return JSONResponse({"status": "queued", "sid": message.sid}, status_code=200)


# # ----------------------------
# # Receive SMS endpoint
# # ----------------------------
# @app.post("/receive-sms")
# @app.get("/receive-sms")
# async def receive_sms(
#     Payload: str | None = Form(default=None),
#     From: str | None = Form(default=None),
#     To: str | None = Form(default=None),
#     Body: str | None = Form(default=None),
# ):
#     try:
#         if Payload:
#             payload_data = json.loads(Payload)
#             msg_data = payload_data.get("webhook", {}).get("request", {}).get("parameters", {})
#             from_number = msg_data.get("From")
#             to_number = msg_data.get("To")
#             body = msg_data.get("Body") or msg_data.get("SmsBody")
#         else:
#             from_number = From
#             to_number = To
#             body = Body

#         print(f"📩 Incoming SMS from {from_number}: {body}")

#         db_msg = Message(
#             sid=None,
#             from_number=from_number,
#             to_number=to_number,
#             body=body,
#             direction="inbound",
#             status="received",
#         )

#         with db.session.begin():
#             db.session.add(db_msg)

#         print("✅ Saved inbound SMS to DB.")

#         resp = MessagingResponse()
#         resp.message("✅ Thanks — we received your message.")
#         return PlainTextResponse(str(resp))

#     except Exception as e:
#         print("Error parsing payload:", e)
#         raise HTTPException(status_code=500, detail="Failed to process incoming SMS")
from fastapi.responses import Response


from openai import OpenAI, APIError
@app.post("/receive-sms")
async def receive_sms(
    request: Request,
    Payload: Optional[str] = Form(None),
    From: Optional[str] = Form(None), 
    To: Optional[str] = Form(None),
    Body: Optional[str] = Form(None)
):
    print(f"🔍 SMS Received - From: {From}, To: {To}, Body: {Body}")
    
    # Parse SMS data (your existing logic)
    if Payload:
        try:
            payload_data = json.loads(Payload)
            msg_data = payload_data.get("webhook", {}).get("request", {}).get("parameters", {})
            from_number = msg_data.get("From")
            to_number = msg_data.get("To")
            body = msg_data.get("Body") or msg_data.get("SmsBody")
        except Exception as e:
            print(f"❌ Error parsing payload: {e}")
            from_number = From
            to_number = To
            body = Body
    else:
        from_number = From
        to_number = To  
        body = Body
    
    print(f"📩 SMS from {from_number} to {to_number}: {body}")
    
    if from_number and body:
        try:
            # Use your existing chat logic!
            # Create ChatRequest object with phone number as user_id
            chat_request = ChatRequest(
                user_id=from_number,  # Phone number becomes user_id
                message=body.strip()
            )
            
            # Call your existing chat function
            chat_response = await chat_with_bot(chat_request)
            
            print(f"✅ Chat Response: {chat_response.bot_message}")
            print(f"📊 Lead Status: {chat_response.lead_status}")
            
            # Create Twilio SMS response
            resp = MessagingResponse()
            resp.message(chat_response.bot_message)
            
            # Return proper XML response for Twilio
            return Response(
                content=str(resp),
                media_type="application/xml",
                headers={"Content-Type": "text/xml; charset=utf-8"}
            )
            
        except Exception as e:
            print(f"❌ SMS Chat Error: {e}")
            
            # Fallback response if chat fails
            resp = MessagingResponse()
            resp.message("Sorry, I'm having technical difficulties. Please try again in a moment.")
            
            return Response(
                content=str(resp),
                media_type="application/xml",
                headers={"Content-Type": "text/xml; charset=utf-8"}
            )
    
    # Default response if missing data
    resp = MessagingResponse()
    resp.message("Hello! Send me a message to get started.")
    
    return Response(
        content=str(resp),
        media_type="application/xml",
        headers={"Content-Type": "text/xml; charset=utf-8"}
    )


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
twilio_sender = None 
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_sender = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("Twilio sender client initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Twilio client: {e}")
else:
    print("WARNING: Twilio client not initialized because SID or Token is missing.")

class OutboundRequest(BaseModel):
    to_number: str
    message: str

@app.post("/send-outbound")
def send_outbound_sms(request: OutboundRequest):
    """
    Sends an initial, unsolicited SMS message using the Twilio REST API.
    """
    try:
        message = twilio_sender.messages.create(
            to=request.to_number,
            from_="+19713768108",  
            body=request.message
        )
        return {"status": "success", "sid": message.sid, "message": "Outbound SMS sent."}
    except Exception as e:
        return {"status": "error", "message": f"Twilio send failed: {e}"}

# account_sid = os.environ["TWILIO_ACCOUNT_SID"]
# auth_token = os.environ["TWILIO_AUTH_TOKEN"]
# client = Client(account_sid, auth_token)
# @app.post("/receive-sms")
# def send_message():
#     try:
#         message = client.messages.create(
#             body="Test message from Twilio to my phone!",
#             from_="+19713768108",   
#             to="+918894037236",     
#         )
        
#         print(f"✅ Message sent successfully!")
#         print(f"Message SID: {message.sid}")
#         print(f"Status: {message.status}")
#         print(f"Body: {message.body}")
        
#         return message.body
        
#     except Exception as e:
#         print(f"❌ Error sending SMS: {e}")
#         return None

# # Run the function
# send_message()




# --- Main entry point for Uvicorn ---
if __name__ == "__main__":
    import uvicorn
    initialize_sqlite_db()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
