from openai import OpenAI
import os
import asyncio
from pydantic import BaseModel
from fastapi import FastAPI
from dotenv import load_dotenv
import time, re

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def create_assistance(FILE_ID):
# 2️⃣ Create vector store
    vector_store = client.vector_stores.create(name="New Vector Store_2")
    print("✔ Vector Store ID:", vector_store.id)

    # 3️⃣ Add file to vector store
    client.vector_stores.files.create(
        vector_store_id=vector_store.id,
        file_id=FILE_ID
    )
    print("✔ File added to Vector Store")



    # WAIT UNTIL FILE IS PROCESSED
   
    while True:
        job_status = client.vector_stores.files.retrieve(
            vector_store_id=vector_store.id,
            file_id=FILE_ID
        )
        print("File status:", job_status.status)
        if job_status.status == "processed" or job_status.status == 'completed':
            print("✔ File processed successfully")
            break
        elif job_status.status == "failed":
            raise Exception("❌ File processing failed")
        time.sleep(2)


    ["ask_name,ask_age,ask_state,ask_health_confirm,ask_health_details,ask_budget,ask_contact_time,confirm_booking,completed_qualification,morning,afternoon,evening,1,2,3,4"]
    # 4️⃣ Create assistant linked to vector store
    assistant = client.beta.assistants.create(
        model="gpt-4o-mini-2024-07-18",
        name="Nia",
        instructions="""
            You are Nia, the virtual assistant for The Paul Group.
            You must analyze the provided JSON dataset containing all approved intents, example user messages, and response templates.

            Your rules:

            1. Intent Matching
            - When the user sends a message, identify the closest matching intent in the JSON.
            - Respond ONLY using the corresponding response from the JSON with minimal changes.
                i) Only fill in personalization slots like {first_name} when provided.
                ii) Do NOT rewrite or rephrase beyond small adjustments needed for grammar or context.
            - You MUST NOT create new information, benefits, claims, or promises.
            - If no relevant intent or answer exists in the JSON, reply exactly with: “I don’t know.”

            2. Lead Form Inputs to Ignore (VERY IMPORTANT)
            The user may share information such as:
            - Full name
            - Age
            - State
            - Health confirmation (Yes/No)
            - Health condition details
            - Monthly budget for premiums
            - Best contact time
            - Selecting or confirming time slots

            These messages are NOT intents and must be COMPLETELY IGNORED.

            If the user sends ANY message that matches or relates to the form fields above,
            you MUST always respond with: “I don’t know.”

            Examples you must ignore:
            - “My name is John”
            - “I am 42”
            - “I live in Texas”
            - “Yes, I have high blood pressure”
            - “My budget is $75”
            - “Evenings work for me”
            - “Option 2 is good”
            - “Yes, confirm it”

            For **all such messages**, you MUST NOT use JSON intents.
            Instead ALWAYS respond: “I don’t know.”

            3. No Improvisation
            - Do NOT answer any question unless explicitly found in the JSON dataset.
            - Do NOT modify the structure, tone, or intent of the provided JSON.
            - Do NOT attempt to help the user with form-related answers.

            Tone:
            - Friendly
            - Professional
            - Very short and direct
            - Consistent with the style found in the JSON

            The JSON file is your single source of truth.
            Nothing outside the JSON is allowed.
        """,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
    )
    print("✔ Assistant ID:", assistant.id,'\n', assistant)
    return assistant.id,vector_store.id


#Question Answer
def ask_assistance(ASSISTANT_ID,USER_MESSAGE):
    thread = client.beta.threads.create()
    print("✔ Thread ID:", thread.id)

    # 6️⃣ Add user question
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=USER_MESSAGE
    )

    # 7️⃣ Run assistant
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID #assistant.id
    )
    print("✔ Run completed")

    # 8️⃣ Fetch assistant response
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    answer = None
    for msg in reversed(messages.data):
        if msg.role == "assistant":
            # print(msg.content,'======Message====')
            for idx, txt in enumerate(msg.content):
                print(txt.text.value,'====txt',idx)
            answer = msg.content[0].text.value
            break
        
    print("\n=====================")
    print("🤖 Assistant Response:")
    # print(answer.split('【')[0])
    print("=====================\n")
    return answer.split('【')[0]





def extract_user_name(text: str) -> str:
    if not text:
        return ""
    
    # Clean and normalize spacing
    text = text.strip().lower()
    
    # List of noise patterns to remove
    noise_patterns = [
        r"^my name is\s+",
        r"^my name's\s+",
        r"^my name\s*:\s*",
        r"^name is\s+",
        r"^name's\s+",
        r"^name\s*:\s*",
        r"^i am\s+",
        r"^i'm\s+",
        r"^this is\s+",
        r"^its\s+",
        r"^it is\s+",
        r"^me\s+"
    ]
    
    # Remove noise words
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text)

    # Remove extra spaces
    text = text.strip()

    # Capitalize each word (clean name)
    return " ".join(word.capitalize() for word in text.split())














    
        # Up on Server==================
        # instructions="""
        #     You are Nia, the virtual assistant for The Paul Group.
        #     You must analyze the provided JSON dataset containing all approved intents, example user messages, and response templates.
        #     When the user sends a message:
        #     - Identify the closest matching intent in the JSON.
        #     - Respond using the corresponding response from the JSON with minimal changes.
        #         i). Only fill in personalization slots like {first_name} when provided.
        #         i). Do NOT rewrite or rephrase beyond small adjustments needed for grammar or context.
        #     - If no relevant intent or answer exists in the JSON, reply with: “I don’t know.”
        #     - Keep answers short, direct, and consistent with the wording in the JSON.
        #     - Do NOT create new information, promises, benefits, or claims not found in the JSON. Just improve it little bit.
        #     - Follow the JSON’s actions, follow-up questions, and structure exactly when applicable.

        #     Your tone should be:
        #     - Friendly
        #     - Professional
        #     - Straight to the point
        #     - Consistent with the style found in the JSON

        #     You are not allowed to improvise outside the dataset.
        #     Always rely on the JSON file as the single source of truth.
        # """,


        # instructions="""
        # You are Nia, the virtual assistant for The Paul Group.
        # You must analyze the provided JSON dataset containing all approved intents, example user messages, and response templates.
        # When the user sends a message:
        # - Identify the closest matching intent in the JSON.
        # - Respond using the corresponding response from the JSON with minimal changes.
        #     i). Only fill in personalization slots like {first_name} when provided.
        #     i). Do NOT rewrite or rephrase beyond small adjustments needed for grammar or context.
        # - If no relevant intent or answer exists in the JSON, reply with: “I don’t know.”
        # - Keep answers short, direct, and consistent with the wording in the JSON.
        # - Do NOT create new information, promises, benefits, or claims not found in the JSON. Just improve it little bit.
        # - Follow the JSON’s actions, follow-up questions, and structure exactly when applicable.

        # Your tone should be:
        # - Friendly
        # - Professional
        # - Straight to the point
        # - Consistent with the style found in the JSON

        # You are not allowed to improvise outside the dataset.
        # Always rely on the JSON file as the single source of truth.

        # -------------------------------------------------------------------
        # ADDITIONAL RULE:
        # If the user message is related to ANY of the following qualification keywords, ALWAYS reply: "I don't know."

        # QUALIFICATION_QUESTIONS = {
        #     "ask_name": "Great! To help us get started, could you please tell me your **full name**?",
        #     "ask_age": "Thanks, [USER_NAME]! What is your **current age**?",
        #     "ask_state": "And what **state** do you currently reside in?",
        #     "ask_health_confirm": "Regarding your **general health**,Excellent! Do you have any major health conditions? (Yes/No) This helps us determine your eligibility?",
        #     "ask_health_details": "Could you briefly mention some of the **major health conditions** you have, so we can assess the best options?",
        #     "ask_budget": "What's your **monthly budget** for premiums? Please let me know how much you're comfortable spending per month (e.g., '$55', '$75', 'around $100').",
        #     "ask_contact_time": "Finally, what's the **best time** for a licensed agent to contact you? (e.g., 'morning', 'afternoon', 'evening', or specific days/times)",
        #     "ask_time_slot_confirmation": "Great! I have some available slots for {time_period}. Which specific time works best for you?\n\n{available_slots}\n\nPlease choose a number (1, 2, 3, etc.) or tell me which time you prefer.",
        #     "confirm_booking": "Perfect! I'll book you for **{selected_slot}**. Can I confirm this appointment time for you? (Yes/No)",
        #     "completed_qualification": "Thank you for providing all the details! We're processing your request.",
        # }

        # If user query matches or is related to ANY of these, respond ONLY with: “I don’t know.”
        # -------------------------------------------------------------------
        # """,