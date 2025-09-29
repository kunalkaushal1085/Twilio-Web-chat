from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal, Dict

SMSLeadQualificationStage = Literal[
    "initial_chat",
    "ask_name",
    "ask_age",
    "ask_state",
    "ask_health_confirm",
    "ask_health_details",
    "ask_budget",
    "ask_contact_time",
    "ask_time_slot_confirmation",
    "confirm_booking",
    "completed_qualification",
    "recruiting_inquiry",
    "recruiting_completed"
]

# Represents a single SMS message
@dataclass
class SMSMessage:
    sender: Literal["user", "bot"]
    text: str
    timestamp: datetime = field(default_factory=datetime.now)

# Represents a lead for SMS flow
@dataclass
class SMSLead:
    id: str
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    age: Optional[int] = None
    state_of_residence: Optional[str] = None
    general_health: Optional[str] = None
    health_conditions: Optional[str] = None
    budget_range: Optional[str] = None
    best_contact_time: Optional[str] = None
    available_slots: Optional[List[str]] = None
    selected_time_slot: Optional[str] = None
    qualification_stage: SMSLeadQualificationStage = "initial_chat"
    conversation_history: List[SMSMessage] = field(default_factory=list)
    last_active_timestamp: datetime = field(default_factory=datetime.now)
    ticket_number: Optional[str] = None
    is_recruiting_inquiry: Optional[bool] = False

# Request schema for SMS chat
@dataclass
class SMSChatRequest:
    user_id: Optional[str]
    message: str

# Response schema for SMS bot
@dataclass
class SMSChatResponse:
    bot_message: str
    lead_status: SMSLeadQualificationStage
    lead_data: Dict
    conversation_history: List[SMSMessage]
    ticket_number: Optional[str]
    user_id: str