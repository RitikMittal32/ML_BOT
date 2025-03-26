from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd 
import psycopg2
from psycopg2.extras import DictCursor  # For dictionary-like results
import urllib3
import os
import time
from dotenv import load_dotenv
from psycopg2 import sql

# Load environment variables from .env file
load_dotenv()

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# MySQL database configuration
db_host = os.getenv("DATABASE_HOST")
db_user = os.getenv("DATABASE_USER")
db_password = os.getenv("DATABASE_PASSWORD")
db_schema = os.getenv("DATABASE_SCHEMA")


db_config = {
    'host': db_host,  # Replace with your MySQL host
    'user': db_user,       # Replace with your MySQL username
    'password': db_password,  # Replace with your MySQL password
    'database': db_schema,  # Replace with your database name
    'port' : 5432
}

app = Flask(__name__)

# Database connection function
def get_db_connection(retries=4, delay=2):
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(**db_config)
            print("Database connection successful!")
            return conn
        except psycopg2.Error as err:
            print(f"Attempt {attempt + 1} failed: {err}")
            if attempt < retries - 1:
                time.sleep(delay)  # Wait before retrying
            else:
                print("Max retries reached. Failed to connect to the database.")
                return None


# # Check if the connection was successful
# conn = get_db_connection()
# if conn:
#     print("Database is connected!")
    
#     # Create a cursor
#     cur = conn.cursor()
    
#     # Execute a query
#     cur.execute("SELECT * FROM dummy_facultydata;")
    
#     # Fetch and print results
#     rows = cur.fetchall()
#     for row in rows:
#         print(row)
    
#     # Close the cursor and connection
#     cur.close()
#     conn.close()
# else:
#     print("Failed to connect to the database.")

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
        print("book: ", book_title)
        if not book_title:
            return jsonify({'fulfillmentText': "Please provide a book title to search for."})

        availability_info = scrape_library_website(book_title)
        response_text = availability_info if availability_info else "Sorry, I couldn't retrieve the book details."
        return jsonify({'fulfillmentText': response_text})

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

def scrape_library_website(book_title):
    # Replace spaces in the book title with '+' for URL encoding
    book_title_query = book_title.replace(" ", "+")

    # The base URL of the library search (replace book title in the query)
    search_url = f"https://lnmiit-opac.kohacloud.in/cgi-bin/koha/opac-search.pl?idx=&limit=&q={book_title_query}&limit=&weight_search=1"

    try:
        response = requests.get(search_url, verify=False, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to retrieve data, status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # Check for single book result page
        single_book = soup.find("div", class_="record")
        if single_book:
            # Extract title
            book_title = single_book.find("h1", class_="title").text.strip()
            
            # Extract author
            author_tag = single_book.find("li", class_="author")
            author = author_tag.text.strip() if author_tag else "Unknown Author"
            
            # Extract publication details
            pub_tag = single_book.find("li", class_="publisher")
            publication = pub_tag.text.strip() if pub_tag else "Unknown Publication"
            
            # Extract call number
            call_number_tag = single_book.find("span", class_="call-number")
            call_number = call_number_tag.text.strip() if call_number_tag else "Unknown Call Number"
            
            # Extract availability/items
            items_table = single_book.find("table", id="item-table")
            availability_info = []
            if items_table:
                for row in items_table.find_all("tr")[1:]:  # Skip header row
                    cols = row.find_all("td")
                    if len(cols) >= 5:
                        item_type = cols[1].text.strip()
                        location = cols[2].text.strip()
                        status = cols[4].text.strip()
                        availability_info.append(f"{item_type} at {location}: {status}")
            
            # Extract holds information
            holds_tag = soup.find('div', id='bib_holds')
            holds = holds_tag.text.strip() if holds_tag else "No holds information available"
            
            # Format the complete response
            response = (
                f"Title: {book_title}\n"
                f"Author: {author}\n"
                f"Publication: {publication}\n"
                f"Call Number: {call_number}\n\n"
                f"Availability:\n"
            )
            
            if availability_info:
                response += "\n".join(availability_info) + "\n\n"
            else:
                response += "No availability information found\n\n"
            
            response += f"Holds Information: {holds}"
            
            return response

        # Find the table that contains the search results
        results_table = soup.find("table", class_="table table-striped")
        
        if not results_table:
            return "No results found."

        # Find all rows in the table (skip header row if exists)
        rows = results_table.find_all("tr")[1:]  # Skip header row
        
        if not rows:
            return "No books found for this search."

        # Lists to store book details
        exact_matches = []
        partial_matches = []
        all_titles = []

        # Loop through the rows and extract book details
        for row in rows:
            title_tag = row.find("a", class_="title")
            if not title_tag:
                continue
                
            title = title_tag.get_text(strip=True)
            all_titles.append(title)
            
            # Check for exact match (case insensitive)
            if book_title.lower() == title.lower():
                author_tag = row.find("ul", class_="author")
                availability_tag = row.find("span", class_="AvailabilityLabel")
                call_number_tag = row.find("span", class_="CallNumber")

                author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"
                availability = availability_tag.get_text(strip=True) if availability_tag else "Unknown Availability"
                call_number = call_number_tag.get_text(strip=True) if call_number_tag else "Unknown Call Number"

                exact_matches.append(f"'{title}' by {author}. {availability} Call number: {call_number}.")
            
            # Check for partial match (substring)
            elif book_title.lower() in title.lower():
                partial_matches.append(title)

        # Return exact match if found
        if exact_matches:
            return exact_matches[0]  # Return first exact match
        
        # If partial matches found, return them as options
        if partial_matches:
            return ("Multiple books found with similar titles. Here are the options:\n\n" + 
                   "\n".join(f"{i+1}. {title}" for i, title in enumerate(partial_matches)) +
                   "\n\nPlease specify which book you're interested in.")
        
        # If no matches at all, return all titles found
        return ("No exact or partial matches found. Here are all books in the search results:\n\n" + 
               "\n".join(f"{i+1}. {title}" for i, title in enumerate(all_titles)) +
               "\n\nPlease specify which book you're interested in.")
    
    except Exception as e:
        print(f"Error in scraping library website: {e}")
        return None



def scrape_admission_details():
    url = "https://lnmiit.ac.in/admissions/ug/regular-mode/"  
    try:
        response = requests.get(url, verify=False, timeout=10)

        if response.status_code != 200:
            print(f"Failed to retrieve data, status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # Find the table containing the admission dates
        admission_table = soup.find("table", class_="table table-bordered")

        if not admission_table:
            print("Could not find the admission details table")
            return None

        rows = admission_table.find_all("tr")
        admission_details = []

        # Iterate over the table rows and collect event and date information
        for i, row in enumerate(rows[1:]):  # Skipping the header row
            columns = row.find_all("td")
            event = columns[0].get_text(strip=True) if columns else "No Event"
            date = columns[1].get_text(strip=True) if columns else "No Date"
            admission_details.append(f"{event} - {date}")

        # Return the first few details (or all if needed)
        if admission_details:
            return "\n\n".join(admission_details)
        else:
            return "No admission details found."
    
    except Exception as e:
        print(f"Error in scraping admission details: {e}")
        return None




def scrape_college_website():
    url = "https://lnmiit.ac.in/events/"
    try:
        response = requests.get(url, verify=False, timeout=10)

        if response.status_code != 200:
            print(f"Failed to retrieve data, status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # Find the div containing the events
        events_container = soup.find("div", class_="em em-view-container")

        if not events_container:
            print("Could not find the events container")
            return None

        # Find the list of events
        events_list_container = events_container.find("div", class_="em pixelbones em-list em-events-list")

        if not events_list_container:
            print("Could not find the events list container")
            return None

        events = events_list_container.find_all("div", class_="em-event em-item")

        first_few_events = []

        for i, event in enumerate(events):
            if i >= 5:
                break

            # Get the event title
            title_tag = event.find("h3", class_="em-item-title")
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            # Get the event date
            date_tag = event.find("div", class_="em-event-date")
            date_text = date_tag.get_text(strip=True) if date_tag else "No Date"

            # Get the event link
            link_tag = title_tag.find("a") if title_tag else None
            link = link_tag['href'] if link_tag else "No Link"

            first_few_events.append(f"{title} - {date_text} - {link}")

        if first_few_events:
            return "\n\n".join(first_few_events)
        else:
            return "No events found."
    except Exception as e:
        print("Error in scraping:", e)
        return None


if __name__ == '__main__':
    app.run(debug=True, port=5000)
