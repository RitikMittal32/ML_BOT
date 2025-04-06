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



@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    
    print("Request:", req)

    intent = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    
    if intent == "GetLatestAnnouncement":
        latest_info = scrape_college_website()
        response_text = latest_info if latest_info else "Sorry, I couldn't retrieve the announcement."
        return jsonify({'fulfillmentText': response_text})
    
    elif intent == "AdmissionDetails":
        latest_info = scrape_admission_details()
        response_text = latest_info if latest_info else "Not able to get required admission info"
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
        if admission_choice:
            details = scrape_college_website(admission_choice)
            return {"fulfillmentText": details}
        elif admission_choice.lower() == 'exit':
            return {
                "fulfillmentText": "Exiting admission information. Type 'Admission Info' to start again.",
                "outputContexts": [
                    {
                        "name": f"{request['session']}/contexts/AdmissionDetails-followup",
                        "lifespanCount": 0
                    }
                ]
            }
        else:
            return jsonify({'fulfillmentText': "Please provide admission choice to search for."})
        
    # Faculty Data Retrieval Intents
    elif intent == "GetPersonByField":
        field_name = req.get('queryResult', {}).get('parameters', {}).get('fieldName', '').strip()
        if not field_name:
            return jsonify({'fulfillmentText': "Please provide a field name to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            query = sql.SQL("""
                SELECT fname, lname, Field, similarity(Field, %s) AS sim
                FROM dummy_facultydata
                WHERE Field %% %s  -- Trigram fuzzy match operator
                ORDER BY sim DESC
                LIMIT 5
            """)
            cursor.execute(query, (field_name, field_name))
            results = cursor.fetchall()

            if results:
                # Filter results with similarity > 0.3
                filtered = [row for row in results if row['sim'] > 0.3]
                if filtered:
                    top_match_field = filtered[0]['field']
                    names = [f"{row['fname']} {row['lname']}" for row in filtered]
                    response_text = (
                        f"Did you mean '{top_match_field}'? "
                        f"Faculty members:\n" + "\n".join(names)
                    )
                else:
                    response_text = f"No relevant matches found for '{field_name}'."
            else:
                response_text = f"No faculty members found in fields similar to '{field_name}'."

        except psycopg2.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."
        finally:
            cursor.close()
            conn.close()

        return jsonify({'fulfillmentText': response_text})

    # --------------------------------------------------------------------------
    # Intent: GetPeopleByDegree (Fuzzy match for degrees like "Mster" -> "M.Sc.")
    # --------------------------------------------------------------------------
    elif intent == "GetPeopleByDegree":
        degree_name = req.get('queryResult', {}).get('parameters', {}).get('DegreeName', '').strip()
        if not degree_name:
            return jsonify({'fulfillmentText': "Please provide a degree to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            query = sql.SQL("""
                SELECT fname, lname, degree, similarity(degree, %s) AS sim
                FROM dummy_facultydata
                WHERE degree %% %s
                ORDER BY sim DESC
                LIMIT 5
            """)
            cursor.execute(query, (degree_name, degree_name))
            results = cursor.fetchall()

            if results:
                filtered = [row for row in results if row['sim'] > 0.3]
                if filtered:
                    top_degree = filtered[0]['degree']
                    names = [f"{row['fname']} {row['lname']}" for row in filtered]
                    response_text = (
                        f"Did you mean '{top_degree}'? "
                        f"Faculty members:\n" + "\n".join(names)
                    )
                else:
                    response_text = f"No relevant matches found for '{degree_name}'."
            else:
                response_text = f"No faculty members found with degrees similar to '{degree_name}'."

        except psycopg2.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."
        finally:
            cursor.close()
            conn.close()

        return jsonify({'fulfillmentText': response_text})

    # --------------------------------------------------------------------------
    # Intent: GetPersonDetails (Fuzzy match for names like "Jhon Doe" -> "John Doe")
    # --------------------------------------------------------------------------
    elif intent == "GetPersonDetails":
        person_name = req.get('queryResult', {}).get('parameters', {}).get('PersonName', '').strip()
        if not person_name:
            return jsonify({'fulfillmentText': "Please provide a faculty name to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            query = sql.SQL("""
                SELECT *, similarity(CONCAT(fname, ' ', lname), %s) AS sim
                FROM dummy_facultydata
                WHERE CONCAT(fname, ' ', lname) %% %s
                ORDER BY sim DESC
                LIMIT 1
            """)
            cursor.execute(query, (person_name, person_name))
            result = cursor.fetchone()

            if result:
                if result['sim'] > 0.4:  # Higher threshold for names
                    details = "\n".join([f"{key}: {value}" for key, value in result.items()])
                    response_text = f"Details for {result['fname']} {result['lname']}:\n{details}"
                else:
                    response_text = f"Did you mean {result['fname']} {result['lname']}? Please confirm."
            else:
                response_text = f"No faculty members found matching '{person_name}'."

        except psycopg2.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."
        finally:
            cursor.close()
            conn.close()

        return jsonify({'fulfillmentText': response_text})

    # --------------------------------------------------------------------------
    # Intent: GetFacultyByGender (No fuzzy matching needed)
    # --------------------------------------------------------------------------
    elif intent == "GetFacultyByGender":
        gender = req.get('queryResult', {}).get('parameters', {}).get('Gender', '').strip().lower()
        if not gender:
            return jsonify({'fulfillmentText': "Please provide a gender to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            query = "SELECT fname, lname FROM dummy_facultydata WHERE gender ILIKE %s"
            cursor.execute(query, (gender,))
            results = cursor.fetchall()

            if results:
                names = [f"{row['fname']} {row['lname']}" for row in results]
                response_text = f"{gender.capitalize()} faculty members:\n" + "\n".join(names)
            else:
                response_text = f"No {gender} faculty members found."

        except psycopg2.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."
        finally:
            cursor.close()
            conn.close()

        return jsonify({'fulfillmentText': response_text})

    else:
        return jsonify({'fulfillmentText': "Unhandled intent."})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
