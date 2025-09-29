"""
Helper functions for The Paul Group chatbot
Contains utility functions for time slot management and budget parsing
"""

from datetime import datetime, timedelta
from typing import Tuple, List
import re


def get_available_time_slots(time_preference: str) -> Tuple[str, List[str]]:
    """
    Generate available time slots based on user's general preference
    Returns (time_period, list_of_slots)
    """
    time_pref_lower = time_preference.lower()
    today = datetime.now()
    
    # If it's late in the day (after 5 PM), start from tomorrow
    if today.hour >= 17:
        start_date = today + timedelta(days=1)  # Tomorrow
        second_date = today + timedelta(days=2)  # Day after tomorrow
    else:
        start_date = today  # Today (if early enough)
        second_date = today + timedelta(days=1)  # Tomorrow
    
    if "morning" in time_pref_lower:
        time_period = "morning"
        slots = [
            f"1. {start_date.strftime('%A, %B %d')} at 9:00 AM",
            f"2. {start_date.strftime('%A, %B %d')} at 10:30 AM", 
            f"3. {second_date.strftime('%A, %B %d')} at 9:00 AM",
            f"4. {second_date.strftime('%A, %B %d')} at 11:00 AM"
        ]
    elif "afternoon" in time_pref_lower:
        time_period = "afternoon" 
        slots = [
            f"1. {start_date.strftime('%A, %B %d')} at 1:00 PM",
            f"2. {start_date.strftime('%A, %B %d')} at 2:30 PM",
            f"3. {second_date.strftime('%A, %B %d')} at 1:00 PM", 
            f"4. {second_date.strftime('%A, %B %d')} at 3:00 PM"
        ]
    elif "evening" in time_pref_lower:
        time_period = "evening"
        slots = [
            f"1. {start_date.strftime('%A, %B %d')} at 6:00 PM",
            f"2. {start_date.strftime('%A, %B %d')} at 7:30 PM",
            f"3. {second_date.strftime('%A, %B %d')} at 6:00 PM",
            f"4. {second_date.strftime('%A, %B %d')} at 7:00 PM"
        ]
    else:
        # Default to mixed times if unclear
        time_period = "various times"
        slots = [
            f"1. {start_date.strftime('%A, %B %d')} at 10:00 AM",
            f"2. {start_date.strftime('%A, %B %d')} at 2:00 PM", 
            f"3. {second_date.strftime('%A, %B %d')} at 10:00 AM",
            f"4. {second_date.strftime('%A, %B %d')} at 6:00 PM"
        ]
    
    return time_period, slots


def parse_slot_selection(user_input: str, available_slots: List[str]) -> Tuple[bool, str]:
    """
    Parse user's slot selection and return (is_valid, selected_slot)
    """
    user_input_lower = user_input.lower().strip()
    
    # Check for number selection (1, 2, 3, 4)
    if user_input_lower in ['1', '2', '3', '4']:
        slot_index = int(user_input_lower) - 1
        if 0 <= slot_index < len(available_slots):
            # Remove the number prefix for cleaner display
            selected_slot = available_slots[slot_index].split('. ', 1)[1]
            return True, selected_slot
    
    # Check for partial time matching in case they type "9am" or "2:30pm"
    for slot in available_slots:
        slot_clean = slot.lower()
        if any(time_part in slot_clean for time_part in user_input_lower.split()):
            selected_slot = slot.split('. ', 1)[1]
            return True, selected_slot
    
    return False, ""


def parse_budget_amount(user_input: str) -> Tuple[bool, str, float]:
    """
    Parse user budget input and return (is_valid, formatted_budget, amount)
    """
    # Remove common words and clean the input
    cleaned_input = re.sub(r'\b(per|month|monthly|around|about|approximately)\b', '', user_input.lower())
    cleaned_input = cleaned_input.replace('$', '').replace(',', '').strip()
    
    # Try to find numbers in the input
    number_matches = re.findall(r'\d+(?:\.\d{1,2})?', cleaned_input)
    
    if not number_matches:
        return False, "", 0.0
    
    # Take the first/largest reasonable number found
    amounts = [float(match) for match in number_matches]
    budget_amount = max(amounts) if amounts else 0
    
    # Validate reasonable range (e.g., $10 to $1000 per month)
    if budget_amount < 10 or budget_amount > 1000:
        return False, "", budget_amount
    
    # Format the budget nicely
    formatted_budget = f"${budget_amount:.0f}/month"
    
    return True, formatted_budget, budget_amount
