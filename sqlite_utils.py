import sqlite3
import json,re,os
from typing import List, Optional, Dict
from schemas import Lead, Message, LeadQualificationStage # Updated import
from datetime import datetime



DATABASE_FILE = "leads.db" 


# Recruiting keywords and phrases
RECRUITING_KEYWORDS = [
    "sales position", "are you hiring", "looking for a job", "want to join your team",
    "is this for agents", "i'm licensed", "i want to get licensed", "work with you",
    "opportunity", "recruiting", "agent position", "sales job", "employment",
    "career", "hiring", "job opening", "work from home", "remote work",
    "commission", "sales opportunity", "insurance agent", "become an agent"
]


# Recruiting response template
RECRUITING_RESPONSE = """Thanks for reaching out! We are actively hiring motivated individuals for final expense sales. You can watch our opportunity video and review the PDF breakdown before scheduling an interview.


🎥 Recruiting Video: [Insert video link]
📄 PDF Opportunity Breakdown: [Insert PDF link]  
📅 Schedule Interview: [Insert Calendly or CRM scheduling link]


Are you already licensed in life insurance, or are you looking to get licensed?"""


# LICENSED_RESPONSE = "Awesome! We work with agents in 16 states. You'll be connected with a manager shortly."
LICENSED_RESPONSE = "Awesome! We work with agents in the states of CA, Alaska, New Mexico, TX, VA, Colorado, Montana, Illinois, Idaho, Utah, Oregon, Nevada, AZ, Hawaii, Wisconsin,Florida. You'll be connected with a manager shortly"


NOT_LICENSED_RESPONSE = "No worries — we help people get licensed and start earning quickly. A recruiter will reach out to you soon."


def migrate_database():
    """Adds missing columns to existing database for backward compatibility."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    try:
        # Check if is_recruiting_inquiry column exists
        cursor.execute("PRAGMA table_info(leads)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_recruiting_inquiry' not in columns:
            print("Adding is_recruiting_inquiry column to existing database...")
            cursor.execute('ALTER TABLE leads ADD COLUMN is_recruiting_inquiry BOOLEAN DEFAULT FALSE')
            conn.commit()
            print("Database migration completed successfully.")
        if 'available_slots' not in columns:
            print("Adding available_slots column to existing database...")
            cursor.execute('ALTER TABLE leads ADD COLUMN available_slots TEXT')
            conn.commit()
        if 'selected_time_slot' not in columns:
            print("Adding selected_time_slot column to existing database...")
            cursor.execute('ALTER TABLE leads ADD COLUMN selected_time_slot TEXT')
            conn.commit()
            print("Time slot columns added successfully.")
        else:
            print("Database is already up to date.")
            
    except sqlite3.Error as e:
        print(f"Error during database migration: {e}")
    finally:
        conn.close()


def initialize_sqlite_db():
    """Initializes the SQLite database and creates the leads table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
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
            qualification_stage TEXT NOT NULL, -- Changed from 'status'
            conversation_history TEXT NOT NULL, -- Stored as JSON string
            last_active_timestamp TEXT NOT NULL, -- Stored as ISO format string
            ticket_number TEXT, -- New field
            is_recruiting_inquiry BOOLEAN DEFAULT FALSE -- New field for recruiting inquiries
        )
    ''')
    conn.commit()
    conn.close()
    print("SQLite database initialized.")
    
    # Run migration to add any missing columns to existing databases
    migrate_database()


def detect_recruiting_inquiry(message: str) -> bool:
    """
    Detects if a message contains recruiting-related keywords or phrases.
    
    Args:
        message (str): The incoming message to analyze
        
    Returns:
        bool: True if recruiting keywords are detected, False otherwise
    """
    message_lower = message.lower().strip()
    
    # Check for direct keyword matches
    for keyword in RECRUITING_KEYWORDS:
        if keyword in message_lower:
            return True
    
    # Additional pattern matching for common recruiting phrases
    recruiting_patterns = [
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
    
    for pattern in recruiting_patterns:
        if re.search(pattern, message_lower):
            return True
    
    return False


def generate_recruiting_response(message: str = None) -> str:
    """
    Generates appropriate recruiting response based on the context.
    
    Args:
        message (str, optional): The original message to analyze for licensing status
        
    Returns:
        str: Appropriate recruiting response
    """
    if message:
        message_lower = message.lower()
        
        # Check if they mention being licensed
        if any(phrase in message_lower for phrase in ["i'm licensed", "i am licensed", "already licensed", "have license","Yes","yes"]):
            return f"{RECRUITING_RESPONSE}\n\n{LICENSED_RESPONSE}"
        
        # Check if they mention wanting to get licensed
        if any(phrase in message_lower for phrase in ["want to get licensed", "need to get licensed", "not licensed", "no license","no","No"]):
            return f"{RECRUITING_RESPONSE}\n\n{NOT_LICENSED_RESPONSE}"
    
    # Default recruiting response asking about licensing status
    return RECRUITING_RESPONSE


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


async def save_lead_to_db(lead: Lead):
    """Saves or updates a lead document in SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()


    lead_dict = lead.model_dump(exclude_none=True) # exclude_none=True will help with optional fields
    
    serialized_history = []
    for msg in lead.conversation_history:
        msg_dict = msg.model_dump()
        # Convert datetime objects within Message to ISO format strings
        msg_dict['timestamp'] = msg_dict['timestamp'].isoformat() 
        serialized_history.append(msg_dict)
    
    # Dump the list of dictionaries (with string timestamps) to a JSON string
    lead_dict['conversation_history'] = json.dumps(serialized_history) 


    # Serialize last_active_timestamp to ISO format string
    lead_dict['last_active_timestamp'] = lead_dict['last_active_timestamp'].isoformat()

    # ADDED: Handle available_slots JSON serialization
    if hasattr(lead, 'available_slots') and lead.available_slots:
        lead_dict['available_slots'] = json.dumps(lead.available_slots)
    else:
        lead_dict['available_slots'] = None


    # Check if this lead has recruiting inquiries in their conversation history
    is_recruiting_inquiry = any(
        detect_recruiting_inquiry(msg.text) 
        for msg in lead.conversation_history 
        if msg.sender == "user"
    )
    lead_dict['is_recruiting_inquiry'] = is_recruiting_inquiry


    # Define all column names and their corresponding values in order
    columns = [
    "id", "phone_number", "full_name", "age", "state_of_residence", 
    "general_health", "health_conditions", "budget_range", 
    "available_slots", "selected_time_slot", "best_contact_time",  # FIXED: Match CREATE TABLE order
    "qualification_stage", "conversation_history", "last_active_timestamp", 
    "ticket_number", "is_recruiting_inquiry"
]
    
    # Prepare values, ensuring None for missing optional fields
    values = [lead_dict.get(col) for col in columns]


    placeholders = ', '.join(['?' for _ in columns])
    column_names_str = ', '.join(columns)


    cursor.execute(f'''
        INSERT OR REPLACE INTO leads ({column_names_str}) 
        VALUES ({placeholders})
    ''', values)
    conn.commit()
    conn.close()
    print(f"Lead {lead.id} saved/updated in SQLite.")


async def get_lead_from_db(lead_id: str) -> Optional[Lead]:
    """Retrieves a lead document from SQLite by ID."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # ADDED: Enable column name access for safety
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
    row = cursor.fetchone()
    conn.close()


    if row:
        # CHANGED: Use column names directly instead of position mapping for safety
        # Handle conversation_history safely
        conversation_history = []
        if row['conversation_history']:
            try:
                raw_history = json.loads(row['conversation_history'])
                for msg_data in raw_history:
                    msg_data['timestamp'] = datetime.fromisoformat(msg_data['timestamp'])
                    conversation_history.append(Message(**msg_data))
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error parsing conversation_history: {e}")
                conversation_history = []

        # ADDED: Handle available_slots safely
        available_slots = None
        if row['available_slots']:
            try:
                available_slots = json.loads(row['available_slots'])
            except (json.JSONDecodeError, TypeError):
                available_slots = None

        # ADDED: Handle last_active_timestamp safely
        last_active_timestamp = datetime.now()
        if row['last_active_timestamp']:
            try:
                last_active_timestamp = datetime.fromisoformat(row['last_active_timestamp'])
            except (TypeError, ValueError):
                last_active_timestamp = datetime.now()


        # Reconstruct Lead object
        lead = Lead(
            id=row['id'],
            phone_number=row['phone_number'],
            full_name=row['full_name'],
            age=row['age'],
            state_of_residence=row['state_of_residence'],
            general_health=row['general_health'],
            health_conditions=row['health_conditions'], 
            budget_range=row['budget_range'],
            best_contact_time=row['best_contact_time'],
            available_slots=available_slots,  # ADDED
            selected_time_slot=row['selected_time_slot'],  # ADDED
            qualification_stage=row['qualification_stage'] or 'initial_chat',  # ADDED: Default fallback
            conversation_history=conversation_history,
            last_active_timestamp=last_active_timestamp,  # CHANGED: Safe handling
            ticket_number=row['ticket_number']
        )
        return lead
    return None


async def get_all_leads_from_db() -> List[Lead]:
    """Retrieves all lead documents from SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # ADDED: Enable column name access
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads')
    rows = cursor.fetchall()
    conn.close()


    all_leads = []

    for row in rows:
        # CHANGED: Use row object directly instead of column mapping
        # Handle conversation_history safely
        conversation_history = []
        if row['conversation_history']:
            try:
                raw_history = json.loads(row['conversation_history'])
                for msg_data in raw_history:
                    msg_data['timestamp'] = datetime.fromisoformat(msg_data['timestamp'])
                    conversation_history.append(Message(**msg_data))
            except (json.JSONDecodeError, TypeError):
                conversation_history = []

        # Handle available_slots safely
        available_slots = None
        if row['available_slots']:
            try:
                available_slots = json.loads(row['available_slots'])
            except (json.JSONDecodeError, TypeError):
                available_slots = None

        # Handle last_active_timestamp safely
        last_active_timestamp = datetime.now()
        if row['last_active_timestamp']:
            try:
                last_active_timestamp = datetime.fromisoformat(row['last_active_timestamp'])
            except (TypeError, ValueError):
                last_active_timestamp = datetime.now()

        lead = Lead(
            id=row['id'],
            phone_number=row['phone_number'],
            full_name=row['full_name'],
            age=row['age'],
            state_of_residence=row['state_of_residence'],
            general_health=row['general_health'],
            health_conditions=row['health_conditions'],
            budget_range=row['budget_range'],
            best_contact_time=row['best_contact_time'],
            available_slots=available_slots,  # ADDED
            selected_time_slot=row['selected_time_slot'],  # ADDED
            qualification_stage=row['qualification_stage'] or 'initial_chat',  # ADDED: Default fallback
            conversation_history=conversation_history,
            last_active_timestamp=last_active_timestamp,  # CHANGED: Safe handling
            ticket_number=row['ticket_number']
        )
        all_leads.append(lead)
    return all_leads


async def get_recruiting_leads_from_db() -> List[Lead]:
    """Retrieves all leads that have made recruiting inquiries."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # ADDED: Enable column name access
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads WHERE is_recruiting_inquiry = 1')
    rows = cursor.fetchall()
    conn.close()


    recruiting_leads = []

    for row in rows:
        # CHANGED: Use row object directly instead of column mapping
        # Handle conversation_history safely
        conversation_history = []
        if row['conversation_history']:
            try:
                raw_history = json.loads(row['conversation_history'])
                for msg_data in raw_history:
                    msg_data['timestamp'] = datetime.fromisoformat(msg_data['timestamp'])
                    conversation_history.append(Message(**msg_data))
            except (json.JSONDecodeError, TypeError):
                conversation_history = []

        # Handle available_slots safely
        available_slots = None
        if row['available_slots']:
            try:
                available_slots = json.loads(row['available_slots'])
            except (json.JSONDecodeError, TypeError):
                available_slots = None

        # Handle last_active_timestamp safely
        last_active_timestamp = datetime.now()
        if row['last_active_timestamp']:
            try:
                last_active_timestamp = datetime.fromisoformat(row['last_active_timestamp'])
            except (TypeError, ValueError):
                last_active_timestamp = datetime.now()

        lead = Lead(
            id=row['id'],
            phone_number=row['phone_number'],
            full_name=row['full_name'],
            age=row['age'],
            state_of_residence=row['state_of_residence'],
            general_health=row['general_health'],
            health_conditions=row['health_conditions'],
            budget_range=row['budget_range'],
            best_contact_time=row['best_contact_time'],
            available_slots=available_slots,  # ADDED
            selected_time_slot=row['selected_time_slot'],  # ADDED
            qualification_stage=row['qualification_stage'] or 'initial_chat',  # ADDED: Default fallback
            conversation_history=conversation_history,
            last_active_timestamp=last_active_timestamp,  # CHANGED: Safe handling
            ticket_number=row['ticket_number']
        )
        recruiting_leads.append(lead)
    return recruiting_leads


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

def _get_latest_file_id() -> Optional[str]:
    """Return file_id from active dataset version, fallback to legacy system."""
    
    # Try to get from versioned system first
    try:
        from sqlite_utils import get_active_dataset_version
        active_version = get_active_dataset_version()
        if active_version and active_version["file_ids"]:
            return active_version["file_ids"][0]  # Use first file from active version
    except:
        pass  # Fall back to legacy system
    
    # Fallback to your original logic
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM uploaded_files ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

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
 
def update_welcome_message(new_message: str) -> None:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE welcome_message SET message = ? WHERE id = 1", (new_message,))
    conn.commit()
    conn.close()
 
 
def ensure_quicklink_table():
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quick_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            active INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
 
 
def get_active_quicklinks() -> list[dict]:
    ensure_quicklink_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, title, description FROM quick_links WHERE active = 1")
    rows = cur.fetchall()
    conn.close()
    return [{"id": row[0], "title": row[1], "description": row[2]} for row in rows]
 
 
def create_quicklink(title: str, description: str) -> dict:
    ensure_quicklink_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quick_links (title, description, active) VALUES (?, ?, 1)",
        (title, description)
    )
    conn.commit()
    link_id = cur.lastrowid
    conn.close()
    return {"id": link_id, "title": title, "description": description}
 
def update_quicklink(link_id: int, title: str, description: str) -> bool:
    ensure_quicklink_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute(
        "UPDATE quick_links SET title = ?, description = ? WHERE id = ?",
        (title, description, link_id)
    )
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success
 
def delete_quicklink(link_id: int) -> bool:
    ensure_quicklink_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM quick_links WHERE id = ?", (link_id,))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success

 
def ensure_theme_table():
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS theme_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            primary_color TEXT,
            background_color TEXT,
            text_color TEXT,
            border_radius INTEGER,
            widget_position TEXT,
            avatar_image_url TEXT,
            welcome_delay INTEGER,
            company_name TEXT,
            logo TEXT,
            body_font_family TEXT,
            body_font_size INTEGER,
            body_font_weight TEXT,
            heading_font_family TEXT,
            heading_font_weight TEXT
                
        )
    """)
    conn.commit()
    conn.close()
 


def get_theme_config() -> dict:
    ensure_theme_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT primary_color, background_color, text_color, border_radius,
               widget_position, avatar_image_url, welcome_delay,company_name,logo,body_font_family, body_font_size, body_font_weight,
               heading_font_family, heading_font_weight
        FROM theme_config WHERE id = 1
    """)
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "primary_color": row[0],
            "background_color": row[1],
            "text_color": row[2],
            "border_radius": row[3],
            "widget_position": row[4],
            "avatar_image_url": row[5],
            "welcome_delay": row[6],
            "company_name": row[7],
            "logo": row[8],
            "body_font_family": row[9],
            "body_font_size": row[10],
            "body_font_weight": row[11],
            "heading_font_family": row[12],
            "heading_font_weight": row[13]
        }
    return {}

 
def update_theme_config(data: dict) -> None:
    ensure_theme_table()
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()

    # Always using id=1 for single config row
    cur.execute("""
        INSERT INTO theme_config (
            id, primary_color, background_color, text_color, border_radius,
            widget_position, avatar_image_url, welcome_delay, company_name, logo,body_font_family, body_font_size, body_font_weight,
            heading_font_family, heading_font_weight
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            primary_color = COALESCE(excluded.primary_color, primary_color),
            background_color = COALESCE(excluded.background_color, background_color),
            text_color = COALESCE(excluded.text_color, text_color),
            border_radius = COALESCE(excluded.border_radius, border_radius),
            widget_position = COALESCE(excluded.widget_position, widget_position),
            avatar_image_url = COALESCE(excluded.avatar_image_url, avatar_image_url),
            welcome_delay = COALESCE(excluded.welcome_delay, welcome_delay),
            company_name = COALESCE(excluded.company_name, company_name),
            logo = COALESCE(excluded.logo, logo),
            body_font_family = COALESCE(excluded.body_font_family, body_font_family),
            body_font_size = COALESCE(excluded.body_font_size, body_font_size),
            body_font_weight = COALESCE(excluded.body_font_weight, body_font_weight),
            heading_font_family = COALESCE(excluded.heading_font_family, heading_font_family),
            heading_font_weight = COALESCE(excluded.heading_font_weight, heading_font_weight)
    """, (
        1,  # ID fixed for single row config
        data.get("primary_color"),
        data.get("background_color"),
        data.get("text_color"),
        data.get("border_radius"),
        data.get("widget_position"),
        data.get("avatar_image_url"),
        data.get("welcome_delay"),
        data.get("company_name"),
        data.get("logo"),
        data.get("body_font_family"),
        data.get("body_font_size"),
        data.get("body_font_weight"),
        data.get("heading_font_family"),
        data.get("heading_font_weight")
    ))

    conn.commit()
    conn.close()



async def get_all_conversations_from_db() -> List[Dict[str, List[Message]]]:
    """
    Retrieves only the conversations from all leads.
    
    Returns:
        List[Dict[str, List[Message]]]: A list of dictionaries with lead ID and conversation history.
    """
    leads = await get_all_leads_from_db()
    conversations = []

    for lead in leads:
        conversations.append({
            "id": lead.id,
            "conversation_history": lead.conversation_history
        })

    return conversations


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
        CREATE TABLE IF NOT EXISTS appointment (
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


def save_appointment_to_db_from_lead(lead) -> int:
    """
    Insert appointment from a confirmed lead object.
    Expects: lead.id, lead.full_name, lead.age, lead.state_of_residence, lead.selected_time_slot, lead.ticket_number
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
        INSERT INTO appointment (lead_id, name, age, state, booking_date, ticket_no, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
 
 
def get_appointments_from_db(lead_id: Optional[str] = None) -> List[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if lead_id:
        cur.execute("SELECT * FROM appointment WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,))
    else:
        cur.execute("SELECT * FROM appointment ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
 
 

def get_appointment_by_id(appt_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM appointment WHERE id = ?", (appt_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None




if __name__ == "__main__":
    # Run tests
    test_recruiting_detection()
