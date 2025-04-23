from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import DictCursor 
from psycopg2 import sql
from functions.Admission import scrape_admission_details
from functions.Events import scrape_college_website
from functions.Library import get_single_book_details, get_book_list, get_single_book_bibilo
from functions.Papers import handle_search_papers_intent
from config.database import get_db_connection




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

    else:
        return jsonify({'fulfillmentText': "Unhandled Intent"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
