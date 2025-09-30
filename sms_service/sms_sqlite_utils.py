# import sqlite3
# import json
# from typing import List, Optional, Dict
# from sms_schemas import SMSLead, SMSMessage, SMSLeadQualificationStage
# from datetime import datetime
# import re

# DATABASE_FILE = "leads.db"

# # Recruiting keywords (same as webchat)
# SMS_RECRUITING_KEYWORDS = [
#     "sales position", "are you hiring", "looking for a job", "want to join your team",
#     "is this for agents", "i'm licensed", "i want to get licensed", "work with you",
#     "opportunity", "recruiting", "agent position", "sales job", "employment",
#     "career", "hiring", "job opening", "work from home", "remote work",
#     "commission", "sales opportunity", "insurance agent", "become an agent"
# ]

# SMS_RECRUITING_RESPONSE = """Thanks for reaching out via SMS! 
# We are actively hiring motivated individuals for final expense sales.

# 🎥 Recruiting Video: [Insert video link]  
# 📄 PDF Opportunity Breakdown: [Insert PDF link]  
# 📅 Schedule Interview: [Insert Calendly or CRM link]

# Are you already licensed in life insurance, or are you looking to get licensed?"""

# SMS_LICENSED_RESPONSE = "Awesome! We work with SMS agents in 16 states. You'll be connected with a manager shortly."
# SMS_NOT_LICENSED_RESPONSE = "No worries — we help SMS applicants get licensed quickly. A recruiter will reach out to you soon."

# def migrate_sms_database():
#     """Adds missing columns for SMS table if not present."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     cursor = conn.cursor()
    
#     try:
#         cursor.execute("PRAGMA table_info(sms_leads)")
#         columns = [col[1] for col in cursor.fetchall()]
        
#         if 'is_recruiting_inquiry' not in columns:
#             cursor.execute('ALTER TABLE sms_leads ADD COLUMN is_recruiting_inquiry BOOLEAN DEFAULT FALSE')
#             conn.commit()
#         if 'available_slots' not in columns:
#             cursor.execute('ALTER TABLE sms_leads ADD COLUMN available_slots TEXT')
#             conn.commit()
#         if 'selected_time_slot' not in columns:
#             cursor.execute('ALTER TABLE sms_leads ADD COLUMN selected_time_slot TEXT')
#             conn.commit()
#     except sqlite3.Error as e:
#         print(f"Error during SMS DB migration: {e}")
#     finally:
#         conn.close()

# def initialize_sms_sqlite_db():
#     """Initializes SQLite DB for SMS leads."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     cursor = conn.cursor()
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS sms_leads (
#             id TEXT PRIMARY KEY,
#             phone_number TEXT,
#             full_name TEXT,
#             age INTEGER,
#             state_of_residence TEXT,
#             general_health TEXT,
#             health_conditions TEXT, 
#             budget_range TEXT,
#             available_slots TEXT,
#             selected_time_slot TEXT,
#             best_contact_time TEXT,
#             qualification_stage TEXT NOT NULL,
#             conversation_history TEXT NOT NULL,
#             last_active_timestamp TEXT NOT NULL,
#             ticket_number TEXT,
#             is_recruiting_inquiry BOOLEAN DEFAULT FALSE
#         )
#     ''')
#     conn.commit()
#     conn.close()
#     migrate_sms_database()
#     print("✅ SMS SQLite DB initialized.")

# def detect_recruiting_inquiry(message: str) -> bool:
#     message_lower = message.lower()
#     # Check keywords
#     if any(keyword in message_lower for keyword in SMS_RECRUITING_KEYWORDS):
#         return True
#     # Regex patterns
#     patterns = [
#         r'\b(job|work|position|career|opportunity|hiring)\b.*\b(insurance|sales|agent)\b',
#         r'\b(insurance|sales|agent)\b.*\b(job|work|position|career|opportunity)\b',
#         r'\blicensed?\b.*\b(insurance|life insurance|agent)\b',
#         r'\bget licensed\b',
#         r'\bjoin.*team\b',
#         r'\bwork.*with.*you\b',
#         r'\bhiring.*agents?\b',
#         r'\bagent.*position\b',
#         r'\bsales.*opportunity\b'
#     ]
#     for pattern in patterns:
#         if re.search(pattern, message_lower):
#             return True
#     return False

# def generate_recruiting_response(message: str = None) -> str:
#     if message:
#         msg_lower = message.lower()
#         if any(phrase in msg_lower for phrase in ["i'm licensed", "i am licensed", "already licensed", "have license","yes"]):
#             return f"{SMS_RECRUITING_RESPONSE}\n\n{SMS_LICENSED_RESPONSE}"
#         if any(phrase in msg_lower for phrase in ["want to get licensed", "not licensed", "no"]):
#             return f"{SMS_RECRUITING_RESPONSE}\n\n{SMS_NOT_LICENSED_RESPONSE}"
#     return SMS_RECRUITING_RESPONSE

# # ------------------------ DB CRUD ------------------------
# def save_lead_to_db(lead: SMSLead):
#     """Insert or update lead in SQLite."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     cursor = conn.cursor()
#     lead_dict = lead.__dict__.copy()

#     # Serialize conversation history
#     serialized_history = []
#     for msg in lead.conversation_history:
#         serialized_history.append({
#             "sender": msg.sender,
#             "text": msg.text,
#             "timestamp": msg.timestamp.isoformat()
#         })
#     lead_dict['conversation_history'] = json.dumps(serialized_history)

#     # Serialize available slots
#     lead_dict['available_slots'] = json.dumps(lead.available_slots) if lead.available_slots else None

#     # Last active timestamp
#     lead_dict['last_active_timestamp'] = lead.last_active_timestamp.isoformat()

#     # Detect recruiting
#     lead_dict['is_recruiting_inquiry'] = any(
#         detect_recruiting_inquiry(msg.text) for msg in lead.conversation_history if msg.sender=="user"
#     )

#     columns = [
#         "id","phone_number","full_name","age","state_of_residence","general_health",
#         "health_conditions","budget_range","available_slots","selected_time_slot",
#         "best_contact_time","qualification_stage","conversation_history",
#         "last_active_timestamp","ticket_number","is_recruiting_inquiry"
#     ]
#     values = [lead_dict.get(col) for col in columns]
#     placeholders = ','.join(['?']*len(columns))
#     cursor.execute(f'''
#         INSERT OR REPLACE INTO sms_leads ({','.join(columns)}) 
#         VALUES ({placeholders})
#     ''', values)
#     conn.commit()
#     conn.close()

# def get_lead_from_db(lead_id: str) -> Optional[SMSLead]:
#     """Retrieve lead by ID."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
#     cursor.execute('SELECT * FROM sms_leads WHERE id=?', (lead_id,))
#     row = cursor.fetchone()
#     conn.close()
#     if row:
#         # Deserialize conversation history
#         history = []
#         try:
#             raw_history = json.loads(row['conversation_history'])
#             for msg in raw_history:
#                 history.append(SMSMessage(
#                     sender=msg['sender'],
#                     text=msg['text'],
#                     timestamp=datetime.fromisoformat(msg['timestamp'])
#                 ))
#         except:
#             history = []

#         available_slots = None
#         if row['available_slots']:
#             try:
#                 available_slots = json.loads(row['available_slots'])
#             except:
#                 available_slots = None

#         last_active = datetime.now()
#         if row['last_active_timestamp']:
#             try:
#                 last_active = datetime.fromisoformat(row['last_active_timestamp'])
#             except:
#                 pass

#         return SMSLead(
#             id=row['id'],
#             phone_number=row['phone_number'],
#             full_name=row['full_name'],
#             age=row['age'],
#             state_of_residence=row['state_of_residence'],
#             general_health=row['general_health'],
#             health_conditions=row['health_conditions'],
#             budget_range=row['budget_range'],
#             best_contact_time=row['best_contact_time'],
#             available_slots=available_slots,
#             selected_time_slot=row['selected_time_slot'],
#             qualification_stage=row['qualification_stage'],
#             conversation_history=history,
#             last_active_timestamp=last_active,
#             ticket_number=row['ticket_number'],
#             is_recruiting_inquiry=row['is_recruiting_inquiry']
#         )
#     return None

# def get_all_leads_from_db() -> List[SMSLead]:
#     """Retrieve all leads."""
#     conn = sqlite3.connect(DATABASE_FILE)
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
#     cursor.execute('SELECT * FROM sms_leads')
#     rows = cursor.fetchall()
#     conn.close()
#     leads = []
#     for row in rows:
#         lead = get_lead_from_db(row['id'])
#         if lead:
#             leads.append(lead)
#     return leads













import sqlite3
import json
from typing import List, Optional
from datetime import datetime
import re
from sms_schemas import LEAD_QUALIFICATION_STAGES

# ------------------------ Data Models ------------------------
class SMSMessage:
    def __init__(self, sender: str, text: str, timestamp: datetime = None):
        self.sender = sender
        self.text = text
        self.timestamp = timestamp or datetime.utcnow()


class SMSLead:
    def __init__(
        self,
        id: str,
        phone_number: str,
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
        last_active_timestamp: datetime = None,
        ticket_number: Optional[str] = None,
        is_recruiting_inquiry: bool = False
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


# ------------------------ Config ------------------------
DATABASE_FILE = "leads.db"

# Recruiting keywords
SMS_RECRUITING_KEYWORDS = [
    "sales position", "are you hiring", "looking for a job", "want to join your team",
    "is this for agents", "i'm licensed", "i want to get licensed", "work with you",
    "opportunity", "recruiting", "agent position", "sales job", "employment",
    "career", "hiring", "job opening", "work from home", "remote work",
    "commission", "sales opportunity", "insurance agent", "become an agent"
]

SMS_RECRUITING_RESPONSE = """Thanks for reaching out via SMS! 
We are actively hiring motivated individuals for final expense sales.

🎥 Recruiting Video: [Insert video link]  
📄 PDF Opportunity Breakdown: [Insert PDF link]  
📅 Schedule Interview: [Insert Calendly or CRM link]

Are you already licensed in life insurance, or are you looking to get licensed?"""

SMS_LICENSED_RESPONSE = "Awesome! We work with SMS agents in 16 states. You'll be connected with a manager shortly."
SMS_NOT_LICENSED_RESPONSE = "No worries — we help SMS applicants get licensed quickly. A recruiter will reach out to you soon."

# ------------------------ DB Setup ------------------------
def migrate_sms_database():
    """Adds missing columns for SMS table if not present."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(sms_leads)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'is_recruiting_inquiry' not in columns:
            cursor.execute('ALTER TABLE sms_leads ADD COLUMN is_recruiting_inquiry BOOLEAN DEFAULT FALSE')
            conn.commit()
        if 'available_slots' not in columns:
            cursor.execute('ALTER TABLE sms_leads ADD COLUMN available_slots TEXT')
            conn.commit()
        if 'selected_time_slot' not in columns:
            cursor.execute('ALTER TABLE sms_leads ADD COLUMN selected_time_slot TEXT')
            conn.commit()
    except sqlite3.Error as e:
        print(f"Error during SMS DB migration: {e}")
    finally:
        conn.close()

def initialize_sms_sqlite_db():
    """Initializes SQLite DB for SMS leads."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_leads (
            id TEXT PRIMARY KEY,
            phone_number TEXT,
            full_name TEXT,
            age INTEGER,
            state_of_residence TEXT,
            general_health TEXT,
            health_conditions TEXT, 
            budget_range TEXT,
            available_slots TEXT,
            selected_time_slot TEXT,
            best_contact_time TEXT,
            qualification_stage TEXT NOT NULL,
            conversation_history TEXT NOT NULL,
            last_active_timestamp TEXT NOT NULL,
            ticket_number TEXT,
            is_recruiting_inquiry BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()
    migrate_sms_database()
    print("✅ SMS SQLite DB initialized.")

# ------------------------ Recruiting Detection ------------------------
def detect_recruiting_inquiry(message: str) -> bool:
    message_lower = message.lower()
    if any(keyword in message_lower for keyword in SMS_RECRUITING_KEYWORDS):
        return True
    
    patterns = [
        r'\b(job|work|position|career|opportunity|hiring)\b.*\b(insurance|sales|agent)\b',
        r'\b(insurance|sales|agent)\b.*\b(job|work|position|career|opportunity)\b',
        r'\blicensed?\b.*\b(insurance|life insurance|agent)\b',
        r'\bget licensed\b',
        r'\bjoin.*team\b',
        r'\bwork.*with.*you\b',
        r'\bhiring.*agents?\b',
        r'\bagent.*position\b',
        r'\bsales.*opportunity\b'
    ]
    for pattern in patterns:
        if re.search(pattern, message_lower):
            return True
    return False

def generate_recruiting_response(message: str = None) -> str:
    if message:
        msg_lower = message.lower()
        if any(phrase in msg_lower for phrase in ["i'm licensed", "i am licensed", "already licensed", "have license","yes"]):
            return f"{SMS_RECRUITING_RESPONSE}\n\n{SMS_LICENSED_RESPONSE}"
        if any(phrase in msg_lower for phrase in ["want to get licensed", "not licensed", "no"]):
            return f"{SMS_RECRUITING_RESPONSE}\n\n{SMS_NOT_LICENSED_RESPONSE}"
    return SMS_RECRUITING_RESPONSE

# ------------------------ DB CRUD ------------------------
def save_lead_to_db(lead: SMSLead):
    """Insert or update lead in SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    lead_dict = lead.__dict__.copy()

    # Serialize conversation history
    serialized_history = [
        {
            "sender": msg.sender,
            "text": msg.text,
            "timestamp": msg.timestamp.isoformat()
        }
        for msg in lead.conversation_history
    ]
    lead_dict['conversation_history'] = json.dumps(serialized_history)

    # Serialize available slots
    lead_dict['available_slots'] = json.dumps(lead.available_slots) if lead.available_slots else None

    # Last active timestamp
    lead_dict['last_active_timestamp'] = lead.last_active_timestamp.isoformat()

    # Detect recruiting
    lead_dict['is_recruiting_inquiry'] = any(
        detect_recruiting_inquiry(msg.text) for msg in lead.conversation_history if msg.sender == "user"
    )

    columns = [
        "id","phone_number","full_name","age","state_of_residence","general_health",
        "health_conditions","budget_range","available_slots","selected_time_slot",
        "best_contact_time","qualification_stage","conversation_history",
        "last_active_timestamp","ticket_number","is_recruiting_inquiry"
    ]
    values = [lead_dict.get(col) for col in columns]
    placeholders = ','.join(['?']*len(columns))
    cursor.execute(f'''
        INSERT OR REPLACE INTO sms_leads ({','.join(columns)}) 
        VALUES ({placeholders})
    ''', values)
    conn.commit()
    conn.close()

def get_lead_from_db(lead_id: str) -> Optional[SMSLead]:
    """Retrieve lead by ID."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sms_leads WHERE id=?', (lead_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        # Deserialize conversation history
        history = []
        try:
            raw_history = json.loads(row['conversation_history'])
            for msg in raw_history:
                history.append(SMSMessage(
                    sender=msg['sender'],
                    text=msg['text'],
                    timestamp=datetime.fromisoformat(msg['timestamp'])
                ))
        except:
            history = []

        available_slots = None
        if row['available_slots']:
            try:
                available_slots = json.loads(row['available_slots'])
            except:
                available_slots = None

        last_active = datetime.now()
        if row['last_active_timestamp']:
            try:
                last_active = datetime.fromisoformat(row['last_active_timestamp'])
            except:
                pass

        return SMSLead(
            id=row['id'],
            phone_number=row['phone_number'],
            full_name=row['full_name'],
            age=row['age'],
            state_of_residence=row['state_of_residence'],
            general_health=row['general_health'],
            health_conditions=row['health_conditions'],
            budget_range=row['budget_range'],
            best_contact_time=row['best_contact_time'],
            available_slots=available_slots,
            selected_time_slot=row['selected_time_slot'],
            qualification_stage=row['qualification_stage'],
            conversation_history=history,
            last_active_timestamp=last_active,
            ticket_number=row['ticket_number'],
            is_recruiting_inquiry=row['is_recruiting_inquiry']
        )
    return None

def get_all_leads_from_db() -> List[SMSLead]:
    """Retrieve all leads."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sms_leads')
    rows = cursor.fetchall()
    conn.close()
    leads = []
    for row in rows:
        lead = get_lead_from_db(row['id'])
        if lead:
            leads.append(lead)
    return leads
