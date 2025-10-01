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
import asyncio
from sms_schemas import LEAD_QUALIFICATION_STAGES


# ------------------------ Variables ------------------------
LICENSED_RESPONSE = "Awesome! We work with agents in the states of CA, Alaska, New Mexico, TX, VA, Colorado, Montana, Illinois, Idaho, Utah, Oregon, Nevada, AZ, Hawaii, Wisconsin,Florida. You'll be connected with a manager shortly"
NOT_LICENSED_RESPONSE = "No worries — we help people get licensed and start earning quickly. A recruiter will reach out to you soon."


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
DATABASE_FILE = "../leads.db"

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
    conn = sqlite3.connect(DATABASE_FILE, timeout=30)
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
async def save_lead_to_db(lead: SMSLead):
    """Insert or update lead in SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    lead_dict = lead.__dict__.copy()

    # Serialize conversation history
    serialized_history = [
        {
            "sender": msg["sender"],
            "text": msg["text"],
            "timestamp": msg["timestamp"].isoformat()
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
        detect_recruiting_inquiry(msg["text"]) for msg in lead.conversation_history if msg["sender"] == "user"
    )

    columns = [
        "id","phone_number","full_name","age","state_of_residence","general_health",
        "health_conditions","budget_range","available_slots","selected_time_slot",
        "best_contact_time","qualification_stage","conversation_history",
        "last_active_timestamp","ticket_number","is_recruiting_inquiry"
    ]
    values = [lead_dict.get(col) for col in columns]
    placeholders = ','.join(['?']*len(columns))

    print('=====Values====\n',values,'\n')
    print('=====placeholders====\n',placeholders,'\n')

    cursor.execute(f'''
        INSERT OR REPLACE INTO sms_leads ({','.join(columns)}) 
        VALUES ({placeholders})
    ''', values)
    conn.commit()
    conn.close()

async def get_lead_from_db(phone_number: str) -> Optional[SMSLead]:
    """Retrieve lead by ID."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sms_leads WHERE phone_number=?', (phone_number,))
    row = cursor.fetchone()
    conn.close()
    if row:
        # Deserialize conversation history
        history = []
        try:
            raw_history = json.loads(row['conversation_history'])
            for msg in raw_history:
                history.append(
                    SMSMessage().load({
                        "sender":msg['sender'],
                        "text":msg['text'],
                        "timestamp":datetime.fromisoformat(msg['timestamp'])
                    })
                )
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


        return SMSLead().load({
            "id":row['id'],
            "phone_number":row['phone_number'],
            "full_name":row['full_name'],
            "age":row['age'],
            "state_of_residence":row['state_of_residence'],
            "general_health":row['general_health'],
            "health_conditions":row['health_conditions'],
            "budget_range":row['budget_range'],
            "best_contact_time":row['best_contact_time'],
            "available_slots":available_slots,
            "selected_time_slot":row['selected_time_slot'],
            "qualification_stage":row['qualification_stage'],
            "conversation_history":history,
            "last_active_timestamp":last_active,
            "ticket_number":row['ticket_number'],
            "is_recruiting_inquiry":row['is_recruiting_inquiry']
        })
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


# Example usage function for testing
def test_recruiting_detection():
    """Test function to verify recruiting detection works correctly."""
    test_messages = [
        "Hi, I'm interested in a sales position",
        "Are you hiring?",
        "Looking for a job opportunity",
        "I want to join your team",
        "Is this for agents?",
        "I'm licensed in life insurance",
        "I want to get licensed",
        "Do you have any career opportunities?",
        "I'm looking for work from home jobs",
        "What insurance do you offer?",  # Should not trigger
        "I need life insurance quotes"   # Should not trigger
    ]
   
    print("Testing recruiting detection:")
    for msg in test_messages:
        is_recruiting = detect_recruiting_inquiry(msg)
        print(f"'{msg}' -> Recruiting: {is_recruiting}")
        if is_recruiting:
            response = generate_recruiting_response(msg)
            print(f"Response: {response[:100]}...")
        print("-" * 50)
 
#working code
def store_uploaded_file_info(file_id: str, chunks_created: int):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
 
    # Create table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            chunks_created INTEGER
        )
    ''')
 
    # Insert record
    cursor.execute('''
        INSERT INTO uploaded_files (file_id, chunks_created)
        VALUES (?, ?)
    ''', (file_id, chunks_created))
 
    conn.commit()
    conn.close()
 
 
# use this code insted of previous
# sqlite_utils.py - ADD these functions to your existing file
 
def ensure_dataset_versions_table():
    """Create versioning table alongside existing uploaded_files table."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
   
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_label TEXT UNIQUE NOT NULL,
            description TEXT,
            total_records INTEGER,
            upload_timestamp TEXT NOT NULL,
            is_active BOOLEAN DEFAULT FALSE,
            file_ids TEXT NOT NULL,
            created_by TEXT
        );
    """)
   
    conn.commit()
    conn.close()
 
def store_versioned_dataset(version_label: str, description: str, file_ids: list,
                           total_records: int, created_by: str = None):
    """Store a versioned dataset and make it active."""
    ensure_dataset_versions_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
   
    try:
        # Deactivate all previous versions
        cursor.execute("UPDATE dataset_versions SET is_active = 0")
       
        # Insert new version as active
        cursor.execute("""
            INSERT INTO dataset_versions
            (version_label, description, total_records, upload_timestamp, is_active, file_ids, created_by)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (
            version_label,
            description,
            total_records,
            datetime.now().isoformat(),
            json.dumps(file_ids),
            created_by
        ))
       
        # Insert into uploaded_files table (in the SAME connection)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT,
                chunks_created INTEGER
            )
        ''')
       
        # Insert each file_id into uploaded_files
        for file_id in file_ids:
            cursor.execute('''
                INSERT INTO uploaded_files (file_id, chunks_created)
                VALUES (?, ?)
            ''', (file_id, len(file_ids)))
       
        conn.commit()
       
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
 
def get_active_dataset_version():
    """Get currently active dataset version."""
    ensure_dataset_versions_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
   
    cursor.execute("""
        SELECT version_label, file_ids, total_records
        FROM dataset_versions
        WHERE is_active = 1
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
   
    if row:
        return {
            "version": row[0],
            "file_ids": json.loads(row[1]),
            "total_records": row[2]
        }
    return None
 
def get_all_dataset_versions():
    """List all dataset versions."""
    ensure_dataset_versions_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
   
    cursor.execute("""
        SELECT version_label, description, total_records, upload_timestamp,
               is_active, created_by
        FROM dataset_versions
        ORDER BY upload_timestamp DESC
    """)
   
    versions = []
    for row in cursor.fetchall():
        versions.append({
            "version": row[0],
            "description": row[1] or "",
            "total_records": row[2],
            "upload_timestamp": row[3],
            "is_active": bool(row[4]),
            "created_by": row[5] or "Unknown"
        })
   
    conn.close()
    return versions
 
def set_active_dataset_version(version_label: str):
    """Switch active dataset version."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
   
    # Check if version exists
    cursor.execute("SELECT id FROM dataset_versions WHERE version_label = ?", (version_label,))
    if not cursor.fetchone():
        conn.close()
        return False
   
    # Deactivate all, then activate the target
    cursor.execute("UPDATE dataset_versions SET is_active = 0")
    cursor.execute("UPDATE dataset_versions SET is_active = 1 WHERE version_label = ?", (version_label,))
   
    conn.commit()
    conn.close()
    return True


def ensure_admin_table() -> None:
    """
    Creates the admin table if it doesn’t exist.
    Columns:
        id        INTEGER autoincrement primary-key
        email     UNIQUE text
        password  bcrypt-hashed text
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()
 
def get_admin_by_email(email: str) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    cur  = conn.cursor()
    cur.execute("SELECT id, email, password FROM admin WHERE email = ?", (email.lower(),))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "email": row[1], "password": row[2]}
    return None
 
 
def create_admin(email: str, hashed_pw: str) -> dict:
    ensure_admin_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO admin (email, password) VALUES (?, ?)",
        (email.lower(), hashed_pw)
    )
    conn.commit()
    admin_id = cur.lastrowid
    conn.close()
    return {"id": admin_id, "email": email.lower()}
 
 
def update_admin_password(admin_id: int, hashed_pw: str) -> None:
    conn = sqlite3.connect(DATABASE_FILE)
    cur  = conn.cursor()
    cur.execute(
        "UPDATE admin SET password = ? WHERE id = ?",
        (hashed_pw, admin_id)
    )
    conn.commit()
    conn.close()
 
#sahil
def ensure_welcome_table():
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS welcome_message (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message TEXT NOT NULL
        )
    """)
    cur.execute("INSERT OR IGNORE INTO welcome_message (id, message) VALUES (1, 'Welcome to the Admin Panel')")
    conn.commit()
    conn.close()
 
def get_welcome_message() -> str:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("SELECT message FROM welcome_message WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""

def handle_licensing_status_response(message: str) -> str:
    """
    Handles follow-up responses about licensing status.
    
    Args:
        message (str): The response about licensing status
        
    Returns:
        str: Appropriate follow-up response
    """
    message_lower = message.lower().strip()
    
    # Positive responses indicating they are licensed
    licensed_indicators = [
        "yes", "licensed", "i'm licensed", "i am licensed", "already licensed",
        "have my license", "got my license", "certified"
    ]
    
    # Negative responses indicating they are not licensed
    not_licensed_indicators = [
        "no", "not licensed", "don't have", "need to get", "want to get",
        "looking to get", "not yet", "working on it"
    ]
    
    if any(indicator in message_lower for indicator in licensed_indicators):
        return LICENSED_RESPONSE
    elif any(indicator in message_lower for indicator in not_licensed_indicators):
        return NOT_LICENSED_RESPONSE
    else:
        # If unclear, ask for clarification
        return "Could you clarify if you currently have a life insurance license? This will help me connect you with the right person."


#Appointment Booking
def ensure_appointment_table():
    """
    Ensures the appointment table exists with a foreign key referencing leads.id,
    and includes columns for name, age, state, booking_date, status (boolean), created_at.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("""
        PRAGMA foreign_keys = ON;
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sms_appointment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL,
            name TEXT NOT NULL,
            age INTEGER,
            state TEXT,
            booking_date TEXT NOT NULL,         -- ISO date string
            ticket_no TEXT NOT NULL,
            status BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()

async def save_appointment_to_db_from_lead(lead) -> int:
    """
    Insert appointment from a confirmed lead object.
    Expects: lead.id, lead.full_name, lead.age, lead.state_of_residence, lead.selected_time_slot
    Sets status=True because booking is confirmed.
    """
    if not getattr(lead, "id", None):
        raise ValueError("Lead object must have an id")
    if not getattr(lead, "selected_time_slot", None):
        raise ValueError("Lead does not have a selected_time_slot")
    if not getattr(lead, "full_name", None):
        raise ValueError("Lead does not have full_name")
 
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    created_at = datetime.now().isoformat()
 
    cur.execute("""
        INSERT INTO sms_appointment (lead_id, name, age, state, booking_date, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        lead.id,
        getattr(lead, "full_name", None),
        getattr(lead, "age", None),
        getattr(lead, "state_of_residence", None),
        getattr(lead, "selected_time_slot", None),
        getattr(lead, "ticket_number", None),
        True,  # confirmed
        created_at
    ))
    conn.commit()
    appt_id = cur.lastrowid
    conn.close()
    return appt_id
 