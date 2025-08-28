from pydantic import BaseModel, Field, ValidationError
from datetime import datetime
from typing import List, Optional, Literal, Dict
import uuid

# Define specific stages for the lead qualification process
# Define specific stages for the lead qualification process
LeadQualificationStage = Literal[
    "initial_chat",       # User is asking general questions
    "ask_name",           # Bot needs to ask for user's full name
    "ask_age",            # Bot needs to ask for user's age
    "ask_state",          # Bot needs to ask for user's state of residence
    "ask_health_confirm", # Bot needs to ask for general health (Yes/No)
    "ask_health_details", # Bot needs to ask for specific conditions if health is 'No'
    "ask_budget",         # Bot needs to ask for budget range
    "ask_contact_time",   # Bot needs to ask for best contact time
    "ask_time_slot_confirmation", # ADD THIS: Bot shows available time slots
    "confirm_booking",    # ADD THIS: Bot asks user to confirm selected slot
    "completed_qualification", # All details collected, ready for confirmation
    # New recruiting stages
    "recruiting_inquiry",    # User has made a recruiting inquiry
    "recruiting_completed"   # Recruiting inquiry has been processed
]


# Represents a single message in the conversation
class Message(BaseModel):
    sender: Literal["user", "bot"] # Sender can only be 'user' or 'bot'
    text: str
    timestamp: datetime = Field(default_factory=datetime.now) # Automatically set current time

# Represents a lead (which in this case, doubles as a chat session)
class Lead(BaseModel):
    id: str = Field(..., description="Unique identifier for the lead/chat session")
    phone_number: Optional[str] = None # Not asked in this flow, but good to keep
    full_name: Optional[str] = None
    age: Optional[int] = None
    state_of_residence: Optional[str] = None
    general_health: Optional[str] = None # Stores "Yes" or "No" initially
    health_conditions: Optional[str] = None # Stores specific conditions if General Health is "No"
    budget_range: Optional[str] = None # e.g., "$50 or less", "$50-$100", "$100+"
    best_contact_time: Optional[str] = None
    available_slots: Optional[List[str]] = None  # List of offered time slots
    selected_time_slot: Optional[str] = None
    # New field to track the current stage of qualification
    qualification_stage: LeadQualificationStage = "initial_chat" 

    conversation_history: List[Message] = Field(default_factory=list) # List of Message objects
    last_active_timestamp: datetime = Field(default_factory=datetime.now) # Last activity time
    ticket_number: Optional[str] = None # To store the unique ticket number
    
    # New field for recruiting inquiries (optional, mainly for database tracking)
    is_recruiting_inquiry: Optional[bool] = False

# Request model for incoming chat messages - UPDATED for anonymous users
class ChatRequest(BaseModel):
    user_id: Optional[str] = Field(None, description="Optional user identifier - will be auto-generated if not provided")
    message: str = Field(..., description="The message text from the user")

# Response model for outgoing bot messages - UPDATED to include user_id
class ChatResponse(BaseModel):
    bot_message: str
    lead_status: LeadQualificationStage # Now reflects the qualification_stage
    lead_data: Dict # Will contain collected lead details for testing/debugging
    conversation_history: List[Message]
    ticket_number: Optional[str] = None # Include ticket number in the response
    user_id: str # Return the user_id so frontend can use it for subsequent requests


class FileUploaded(BaseModel):
    file_id: str
    chunks_created: int
    uploaded_at: Optional[str] = None


    
