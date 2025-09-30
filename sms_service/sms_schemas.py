# from datetime import datetime
# from marshmallow import Schema, fields, validate

# # Define the stages (similar to Literal in FastAPI)
# LEAD_QUALIFICATION_STAGES = [
#     "initial_chat",
#     "ask_name",
#     "ask_age",
#     "ask_state",
#     "ask_health_confirm",
#     "ask_health_details",
#     "ask_budget",
#     "ask_contact_time",
#     "ask_time_slot_confirmation",
#     "confirm_booking",
#     "completed_qualification",
#     "recruiting_inquiry",
#     "recruiting_completed"
# ]

# # Represents a single message in the conversation
# class SMSMessageSchema(Schema):
#     sender = fields.Str(required=True, validate=validate.OneOf(["user", "bot"]))
#     text = fields.Str(required=True)
#     timestamp = fields.DateTime(load_default=lambda: datetime.utcnow())

# # Represents a lead/chat session
# class SMSLeadSchema(Schema):
#     id = fields.Str(required=True)
#     phone_number = fields.Str(required=False, allow_none=True)
#     full_name = fields.Str(required=False, allow_none=True)
#     age = fields.Int(required=False, allow_none=True)
#     state_of_residence = fields.Str(required=False, allow_none=True)
#     general_health = fields.Str(required=False, allow_none=True)  # "Yes" or "No"
#     health_conditions = fields.Str(required=False, allow_none=True)
#     budget_range = fields.Str(required=False, allow_none=True)
#     best_contact_time = fields.Str(required=False, allow_none=True)
#     available_slots = fields.List(fields.Str(), required=False, allow_none=True)
#     selected_time_slot = fields.Str(required=False, allow_none=True)

#     qualification_stage = fields.Str(
#         required=True,
#         validate=validate.OneOf(LEAD_QUALIFICATION_STAGES),
#     )

#     conversation_history = fields.List(fields.Nested(SMSMessageSchema), load_default=list)
#     last_active_timestamp = fields.DateTime(load_default=lambda: datetime.utcnow())
#     ticket_number = fields.Str(required=False, allow_none=True)

#     is_recruiting_inquiry = fields.Bool(required=False, load_default=False)

# # Request model for incoming chat messages
# class SMSChatRequestSchema(Schema):
#     user_id = fields.Str(required=False, allow_none=True)
#     message = fields.Str(required=True)

# # Response model for outgoing bot messages
# class SMSChatResponseSchema(Schema):
#     bot_message = fields.Str(required=True)
#     lead_status = fields.Str(required=True, validate=validate.OneOf(LEAD_QUALIFICATION_STAGES))
#     lead_data = fields.Dict(required=True)
#     conversation_history = fields.List(fields.Nested(SMSMessageSchema))
#     ticket_number = fields.Str(required=False, allow_none=True)
#     user_id = fields.Str(required=True)









from datetime import datetime
from marshmallow import Schema, fields, validate
from typing import List, Optional


# --- Lead Stages ---
LEAD_QUALIFICATION_STAGES = [
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

# --- Data Models (used in app.py directly) ---
class SMSMessage:
    def __init__(self, sender: str, text: str, timestamp: Optional[datetime] = None):
        self.sender = sender
        self.text = text
        self.timestamp = timestamp or datetime.utcnow()


class SMSLead:
    def __init__(
        self,
        id: str,
        phone_number: Optional[str] = None,
        full_name: Optional[str] = None,
        age: Optional[int] = None,
        state_of_residence: Optional[str] = None,
        general_health: Optional[str] = None,
        health_conditions: Optional[str] = None,
        budget_range: Optional[str] = None,
        best_contact_time: Optional[str] = None,
        available_slots: Optional[List[str]] = None,
        selected_time_slot: Optional[str] = None,
        qualification_stage: str = "initial_chat",
        conversation_history: Optional[List[SMSMessage]] = None,
        last_active_timestamp: Optional[datetime] = None,
        ticket_number: Optional[str] = None,
        is_recruiting_inquiry: bool = False,
    ):
        self.id = id
        self.phone_number = phone_number
        self.full_name = full_name
        self.age = age
        self.state_of_residence = state_of_residence
        self.general_health = general_health
        self.health_conditions = health_conditions
        self.budget_range = budget_range
        self.best_contact_time = best_contact_time
        self.available_slots = available_slots or []
        self.selected_time_slot = selected_time_slot
        self.qualification_stage = qualification_stage
        self.conversation_history = conversation_history or []
        self.last_active_timestamp = last_active_timestamp or datetime.utcnow()
        self.ticket_number = ticket_number
        self.is_recruiting_inquiry = is_recruiting_inquiry


# --- Marshmallow Schemas (for validation/serialization) ---
class SMSMessageSchema(Schema):
    sender = fields.Str(required=True, validate=validate.OneOf(["user", "bot"]))
    text = fields.Str(required=True)
    timestamp = fields.DateTime(load_default=lambda: datetime.utcnow())


class SMSLeadSchema(Schema):
    id = fields.Str(required=True)
    phone_number = fields.Str(required=False, allow_none=True)
    full_name = fields.Str(required=False, allow_none=True)
    age = fields.Int(required=False, allow_none=True)
    state_of_residence = fields.Str(required=False, allow_none=True)
    general_health = fields.Str(required=False, allow_none=True)
    health_conditions = fields.Str(required=False, allow_none=True)
    budget_range = fields.Str(required=False, allow_none=True)
    best_contact_time = fields.Str(required=False, allow_none=True)
    available_slots = fields.List(fields.Str(), required=False, allow_none=True)
    selected_time_slot = fields.Str(required=False, allow_none=True)

    qualification_stage = fields.Str(
        required=True,
        validate=validate.OneOf(LEAD_QUALIFICATION_STAGES),
    )

    conversation_history = fields.List(fields.Nested(SMSMessageSchema), load_default=list)
    last_active_timestamp = fields.DateTime(load_default=lambda: datetime.utcnow())
    ticket_number = fields.Str(required=False, allow_none=True)
    is_recruiting_inquiry = fields.Bool(required=False, load_default=False)


# --- API Request/Response Schemas ---
class SMSChatRequestSchema(Schema):
    user_id = fields.Str(required=False, allow_none=True)
    message = fields.Str(required=True)


class SMSChatResponseSchema(Schema):
    bot_message = fields.Str(required=True)
    lead_status = fields.Str(required=True, validate=validate.OneOf(LEAD_QUALIFICATION_STAGES))
    lead_data = fields.Dict(required=True)
    conversation_history = fields.List(fields.Nested(SMSMessageSchema))
    ticket_number = fields.Str(required=False, allow_none=True)
    user_id = fields.Str(required=True)
