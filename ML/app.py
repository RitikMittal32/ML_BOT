from flask import Flask, request, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor 
from psycopg2 import sql
from functions.Admission import scrape_admission_details
from functions.Events import scrape_college_website
from functions.Library import get_single_book_details, get_book_list, get_single_book_bibilo
from functions.Papers import handle_search_papers_intent
from config.database import get_db_connection
from datetime import datetime


app = Flask(__name__)

def get_display_info(session_id):
    display_name = session_id.split('_')[1] if 'session_' in session_id else 'unknown'
    display_name = display_name.upper()

 
    role = display_name
    for keyword in ["BH1", "BH2", "BH3", "BH4", "BH5"]:
        if keyword in display_name:
            return display_name, keyword
        
    for keyword in ["CHIEF WARDEN", "CW", "WARDEN", "22UCS207"]:
        if keyword in display_name:
            return display_name, "warden"
    
        # Typical roll number like 22UEC111
        

    return display_name, role


@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    session_full = req.get('session', '')  # Full session string
    print(session_full)
    session_id = session_full.split('/')[-1]  # Extract just the ID
    display_name = session_id.split('_')[1] if 'session_' in session_id else 'unknown'
    display_name, role = get_display_info(session_id)
    print(display_name, role)
    print("Request:", req)
    intent = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    
    if intent == "GetLatestAnnouncement":
        latest_info = scrape_college_website()
        response_text = latest_info if latest_info else "Sorry, I couldn't retrieve the announcement."
        return jsonify({'fulfillmentText': response_text})    
    elif intent == "SearchLibraryBooks":
        book_title = req.get('queryResult', {}).get('parameters', {}).get('book_title', '')
        if not book_title:
            return jsonify({'fulfillmentText': "Please provide a book title to search for."})
        session = req.get('session', '')
        result = get_book_list(book_title)
        response = {
            'fulfillmentText': result,
            'outputContexts': [
                {
                    'name': f"{session}/contexts/SearchLibraryBooks-followup",
                    'lifespanCount': 0  # Always close followup context by default
                },
                {
                    'name': f"{session}/contexts/awaiting_selection",
                    'lifespanCount': 0  # Close selection context by default
                }
            ]
        }
        if "Title:" in result:  # Single book case
            pass
        elif any(no_result_msg in result for no_result_msg in [
            "No matching books found",
            "No books found", 
            "No books found matching your search",
            "The search returned no results",
            "No results found"
        ]): 
            pass
        else:  # Multiple books case
            response['outputContexts'] = [
                {
                    'name': f"{session}/contexts/awaiting_selection",
                    'lifespanCount': 1,  # Keep context open for selection
                    'parameters': {
                        'original_query': book_title,
                        'search_results': result
                    }
                },
                {
                    'name': f"{session}/contexts/SearchLibraryBooks-followup", 
                    'lifespanCount': 1  # Keep followup context open
                }
            ]
        return jsonify(response)

    elif intent == "SelectBookFromList":
        parameters = req.get('queryResult', {}).get('parameters', {})
        book_choice = parameters.get('book_choice', '')
        biblo_choice = parameters.get('biblo_choice', '')
        
        if book_choice and not biblo_choice:
            # User selected by book title/number only
            details = get_single_book_details(book_choice)
            return {"fulfillmentText": details}
        elif biblo_choice:
            # User included biblionumber (handle as needed)
            details = get_single_book_bibilo(book_choice, biblo_choice)
            return {"fulfillmentText": details}
        else:
            return jsonify({'fulfillmentText': "Please provide a book title to search for."})

    elif intent == "SearchPapers":
        return handle_search_papers_intent(req)
        

    elif intent == "AdmissionData":
        parameters = req.get('queryResult', {}).get('parameters', {})
        admission_choice = parameters.get('admission_choice', '').strip()

        session = req.get('session', '')
        
        if admission_choice.lower() == 'exit info':
            return {
                "fulfillmentText": "Exiting admission information. Type 'Admission Info' to start again.",
                "outputContexts": [
                    {
                        "name": f"{session}/contexts/AdmissionDetails-followup",
                        "lifespanCount": 0
                    }
                ]
            }
        elif admission_choice:
            details = scrape_admission_details(admission_choice)
            return {"fulfillmentText": details}
        else:
            return jsonify({'fulfillmentText': "Please provide admission choice to search for."})
    
    elif intent == "Complaint - custom":
        parameters = req.get('queryResult', {}).get('parameters', {})
        complaint_data = parameters.get('complaint_text', [])

        if isinstance(complaint_data, list) and len(complaint_data) == 1:
            parts = [x.strip() for x in complaint_data[0].split(',')]
            if len(parts) >= 4: 
                # Extract parts and convert hostel to lowercase
                complaint = parts[0]
                hostel = parts[1].strip().upper()  # Ensure hostel is lowercase
                room_no = parts[2]
                date = parts[3]

                conn = get_db_connection()
                # conn=False
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            insert_query = """
                            INSERT INTO complaint (complaint, hostel, room_no, date, issue_solved, roll_no)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """
                            cursor.execute(insert_query, (complaint, hostel, room_no, date, False, role))
                            conn.commit()
                            # Return success message here after successful insertion
                            return jsonify({'fulfillmentText': "Complaint saved successfully!"})    
                    except psycopg2.Error as e:
                        return jsonify({'fulfillmentText': f"Database error: {str(e)}"})
                    finally:
                        conn.close()
    
                else:
                    # Handle database connection failure
                    return jsonify({'fulfillmentText': "Failed to connect to the database."})
            else:
                # Not enough parts provided
                return jsonify({'fulfillmentText': "Please provide full complaint details: issue, hostel, room, date."})
        else:
            # Invalid complaint_data format
            return jsonify({'fulfillmentText': "Invalid complaint format. Please provide data as a list with one string."})
        
    elif intent == "complain-Data":
        parameters = req.get('queryResult', {}).get('parameters', {})

        if role:
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # Warden can see all complaints
                        if role == "warden":
                            select_query = """
                            SELECT roll_no, complaint, room_no, date, hostel 
                            FROM complaint;
                            """
                            cursor.execute(select_query)

                        # Hostel support can see only their own hostel complaints
                        elif role in ["BH1", "BH2", "BH3", "BH4", "BH5"]:
                            select_query = """
                            SELECT roll_no, complaint, room_no, date, hostel 
                            FROM complaint
                            WHERE hostel = %s;
                            """
                            cursor.execute(select_query, (role.upper(),))  # Hostel names likely stored in uppercase

                        else:
                            return jsonify({'fulfillmentText': "You do not have permission to view complaints."})

                        rows = cursor.fetchall()

                        if not rows:
                            return jsonify({'fulfillmentText': "No complaints found."})

                        # Format each complaint
                        response_lines = []
                        for idx, row in enumerate(rows, start=1):
                            roll_no, complaint, room_no, date, hostel = row
                            response_lines.append(
                                f"Complaint {idx}: {complaint}, Room: {room_no}, Hostel: {hostel}, Date: {date}, Filed by: {roll_no}"
                            )

                        response_text = "\n".join(response_lines)
                        return jsonify({'fulfillmentText': response_text})

                except psycopg2.Error as e:
                    return jsonify({'fulfillmentText': f"Database error: {str(e)}"})

                finally:
                    conn.close()
        else:
            return jsonify({'fulfillmentText': "Please specify your role or hostel name to search for complaints."})

    elif intent == "ViewAvailableSlots":
        parameters = req.get('queryResult', {}).get('parameters', {})
        
        # Get parameters from the chatbot request
        faculty_id = parameters.get('last-name')
        date = parameters.get('date') # This will be in YYYY-MM-DDTHH:MM:SS format
        print("vraj")
        print(faculty_id)
        print(date)
        if date:
            # Truncate date parameter to match Spring Boot format (YYYY-MM-DD)
            date = date.split('T')[0]
        
        if not faculty_id or not date:
            # Should be handled by Dialogflow if parameters are required, but good check
            return jsonify({'fulfillmentText': "Please provide a faculty ID and date."})

        response_text = get_available_slots_from_api(faculty_id, date)
        
        # If slots are available, set context to await selection
        if "Here are the available slots" in response_text:
            return jsonify({
                'fulfillmentText': response_text,
                'outputContexts': [
                    {
                        'name': f"{session_full}/contexts/awaiting_slot_selection",
                        'lifespanCount': 2,
                        'parameters': {
                            'faculty_id': faculty_id,
                            'date': date
                        }
                    }
                ]
            })
        else:
            return jsonify({'fulfillmentText': response_text})


   






# This intent handles the user selecting one of the slots (e.g., "book 10:30-11:00")
    elif intent == "ConfirmSlotBooking":
        parameters = req.get('queryResult', {}).get('parameters', {})
        
        # Get parameters from the context set above (from ViewAvailableSlots intent)
        context_params = {}
        session_full = req.get('session')
        
        for context in req.get('queryResult', {}).get('outputContexts', []):
            if 'awaiting_slot_selection' in context['name']:
                context_params = context['parameters']
                break
        
        # 1. Get Faculty ID and Date from the context
        faculty_id = context_params.get('faculty_id')
        date = context_params.get('date') 
        
        # 2. Get the actual slot selection (the ID) from the current user input
        slot_range = parameters.get('slot_range') # e.g., "10:30-11:00"
    
        # Use the full range as the primary slot ID
        slot_id = slot_range 
    
        if not faculty_id or not date or not slot_id:
            # If essential data is missing, fail and close context
            return jsonify({
                'fulfillmentText': "I seem to have lost the booking details. Please start over.",
                'outputContexts': [{'name': f"{session_full}/contexts/awaiting_slot_selection", 'lifespanCount': 0}]
            })
    
        # --- NEW LOGIC TO SATISFY BookingRequest FIELDS ---
        try:
            # Extract start and end times from the slot range
            start_time, end_time = slot_id.split('-')
            
            # Calculate duration in minutes (required by the Java class)
            duration = calculate_duration_minutes(start_time, end_time)
            
        except ValueError:
            # Handle case where slot_id is not in the expected format (e.g., "10:30")
            return jsonify({'fulfillmentText': "Invalid slot format received. Please try again."})
        
        # 3. Use the 'role' derived from the session as the student identifier (studentUid)
        student_uid = role 
        
        # 4. Define the COMPLETE payload matching the required Java BookingRequest structure
        payload = {
            "facultyId": faculty_id,
            "date": date,
            "slotId": slot_id,
            "studentUid": student_uid,
            "duration": duration,   # Added
            "startTime": start_time,# Added
            "endTime": end_time     # Added
        }
        
        # NOTE: The book_slot_via_api function signature needs to change to accept this payload.
        # Assuming the API call handles packaging the data correctly.
        # We will pass the full payload dictionary:
        response_text = book_slot_via_api(payload) # Changed to accept one payload dictionary
    
        # Remove the context after booking attempt (success or failure)
        return jsonify({
            'fulfillmentText': response_text,
            'outputContexts': [
                {
                    'name': f"{session_full}/contexts/awaiting_slot_selection",
                    'lifespanCount': 0 # Close the context
                }
            ]
        })

    else:
        return jsonify({'fulfillmentText': "Unhandled Intent"})



SLOTS_API_BASE_URL = 'https://facultyslots.onrender.com/api/slots'

# Helper function to calculate duration in minutes
def calculate_duration_minutes(start_str, end_str):
    """Calculates the time difference in minutes between two HH:MM strings."""
    try:
        # Define a consistent date part for comparison (date doesn't matter, only time difference)
        base_date = '1970-01-01 '
        
        # Parse the full datetime objects
        start_dt = datetime.strptime(base_date + start_str, '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(base_date + end_str, '%Y-%m-%d %H:%M')
        
        # Calculate difference and convert to minutes
        duration = (end_dt - start_dt).total_seconds() / 60
        return int(duration)
    except Exception:
        # Fallback if parsing fails
        return 30 # Default to 30 minutes if calculation fails



def get_available_slots_from_api(faculty_id, date):
    """Calls Spring Boot GET endpoint to fetch available slots."""
    try:
        url = f"{SLOTS_API_BASE_URL}?facultyId={faculty_id}&date={date}"
        response = requests.get(url)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        slots = response.json()
        
        if not slots:
            return "I found no available slots for that date."
            
        # Format slots for the user
        response_text = "Here are the available slots:\n"
        for idx, slot in enumerate(slots, 1):
            response_text += f"{idx}. {slot.get('start')} - {slot.get('end')}\n"
            
        return response_text
        
    except requests.exceptions.RequestException as e:
        print(f"API Error fetching slots: {e}")
        return "I'm sorry, I couldn't connect to the booking system right now."


def book_slot_via_api(faculty_id, date, slot_id, student_uid):
    """Calls Spring Boot POST endpoint to book a slot."""
    try:
        url = f"{SLOTS_API_BASE_URL}/book"
        payload = {
            "facultyId": faculty_id,
            "date": date,
            "slotId": slot_id,
            "studentUid": student_uid # UNSECURED: Matches Spring Boot implementation
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            return "Your slot has been successfully booked!"
        
        elif response.status_code == 409:
            # Conflict status from Spring Boot (e.g., slot already booked)
            error_data = response.json()
            return f"Booking failed: {error_data.get('error', 'The slot is no longer available.')}"
            
        else:
            # General API error
            error_data = response.json()
            return f"An error occurred while confirming the booking. Code {response.status_code}. {error_data.get('error', '')}"

    except requests.exceptions.RequestException as e:
        print(f"API Error booking slot: {e}")
        return "I'm sorry, there was a system error when trying to book."


if __name__ == '__main__':
    app.run(debug=True, port=5000)










