from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd 
import pymysql
import urllib3
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# MySQL database configuration
db_config = {
    'host': os.getenv("DATABASE_HOST"),  # Replace with your MySQL host
    'user': os.getenv("DATABASE_USER"),       # Replace with your MySQL username
    'password': os.getenv("DATABSE_PASSWORD"),  # Replace with your MySQL password
    'database': os.getenv("DATABASE_SCHEMA"),  # Replace with your database name
    'cursorclass': pymysql.cursors.DictCursor  # Use DictCursor for dictionary results
}

app = Flask(__name__)

# Database connection Function
def get_db_connection():
    try:
        # Attempt to connect to the database
        conn = pymysql.connect(**db_config)
        print("Database connection successful!")
        return conn
    except pymysql.Error as err:
        # Handle connection errors
        print(f"Error connecting to the database: {err}")
        return None

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
        field_name = req.get('queryResult', {}).get('parameters', {}).get('fieldName', '')
        if not field_name:
            return jsonify({'fulfillmentText': "Please provide a field name to search for."})

        # Connect to MySQL
        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor()  # No need for dictionary=True

            # Query the database
            query = "SELECT FName, LName FROM dummy_facultydata WHERE Field = %s"
            cursor.execute(query, (field_name,))
            result = cursor.fetchall()

            # Format the response
            if result:
                names = [f"{row['FName']} {row['LName']}" for row in result]
                response_text = f"Faculty members in {field_name}:\n" + "\n".join(names)
            else:
                response_text = f"No faculty members found in {field_name}."

        except pymysql.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."

        finally:
            # Close the connection
            if 'cursor' in locals():
                cursor.close()
            if conn:
                conn.close()

        return jsonify({'fulfillmentText': response_text})
    
    elif intent == "GetFacultyByGender":
        gender = req.get('queryResult', {}).get('parameters', {}).get('Gender', '')
        if not gender:
            return jsonify({'fulfillmentText': "Please provide a gender to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor()

            query = "SELECT FName, LName FROM dummy_facultydata WHERE Gender = %s"
            cursor.execute(query, (gender,))
            result = cursor.fetchall()

            if result:
                names = [f"{row['FName']} {row['LName']}" for row in result]
                response_text = f"{gender} faculty members:\n" + "\n".join(names)
            else:
                response_text = f"No {gender} faculty members found."

        except pymysql.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."

        finally:
            # Close the connection
            if 'cursor' in locals():
                cursor.close()
            if conn:
                conn.close()

        return jsonify({'fulfillmentText': response_text})
    
    elif intent == "GetPersonDetails":
        person_name = req.get('queryResult', {}).get('parameters', {}).get('PersonName', '')
        if not person_name:
            return jsonify({'fulfillmentText': "Please provide a faculty name to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor()

            query = "SELECT * FROM dummy_facultydata WHERE CONCAT(FName, ' ', LName) = %s"
            cursor.execute(query, (person_name,))
            result = cursor.fetchone()

            if result:
                response_text = f"Details for {person_name}:\n" + "\n".join([f"{key}: {value}" for key, value in result.items()])
            else:
                response_text = f"No details found for {person_name}."

        except pymysql.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."

        finally:
            # Close the connection
            if 'cursor' in locals():
                cursor.close()
            if conn:
                conn.close()

        return jsonify({'fulfillmentText': response_text})
    
    elif intent == "GetPeopleByDegree":
        degree_name = req.get('queryResult', {}).get('parameters', {}).get('DegreeName', '')
        if not degree_name:
            return jsonify({'fulfillmentText': "Please provide a degree to search for."})

        conn = get_db_connection()
        if not conn:
            return jsonify({'fulfillmentText': "Failed to connect to the database."})

        try:
            cursor = conn.cursor()

            query = "SELECT FName, LName FROM dummy_facultydata WHERE Degree = %s"
            cursor.execute(query, (degree_name,))
            result = cursor.fetchall()

            if result:
                names = [f"{row['FName']} {row['LName']}" for row in result]
                response_text = f"Faculty members with {degree_name}:\n" + "\n".join(names)
            else:
                response_text = f"No faculty members found with {degree_name}."

        except pymysql.Error as err:
            print(f"Database error: {err}")
            response_text = "An error occurred while fetching data."

        finally:
            # Close the connection
            if 'cursor' in locals():
                cursor.close()
            if conn:
                conn.close()

        return jsonify({'fulfillmentText': response_text})
        
    else:
        print("Intent not recognized:", intent) 
        return jsonify({'fulfillmentText': "Intent not recognized"})

def scrape_library_website(book_title):
    # Replace spaces in the book title with '+' for URL encoding
    book_title_query = book_title.replace(" ", "+")

    # The base URL of the library search (replace book title in the query)
    search_url = f"https://lnmiit-opac.kohacloud.in/cgi-bin/koha/opac-search.pl?idx=&limit=&q={book_title_query}&limit=&weight_search=1"

    try:
        response = requests.get(search_url, verify=False, timeout=10)
        print("repsonse: ",response)

        if response.status_code != 200:
            print(f"Failed to retrieve data, status code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # Find the table that contains the search results
        results_table = soup.find("table", class_="table table-striped")
        single_book=soup.find("div",class_="record")

        if single_book:
        # For a single book result
            book_title=single_book.find("h1",class_="title").text.strip()
            
            

            holds = soup.find('div', id='bib_holds').text.strip()

            return f"'{book_title}' is available in library \n \n At present {holds}"


        if not results_table:
            print("Could not find the search results table")
            return "No results found."

        # Find all rows in the table
        rows = results_table.find_all("tr")

        if not rows:
            return "No books found for this search."

        # List to store book details
        books_info = []

        # Loop through the rows and extract book details
        for row in rows:
            title_tag = row.find("a", class_="title")
            author_tag = row.find("ul", class_="author")
            availability_tag = row.find("span", class_="AvailabilityLabel")
            call_number_tag = row.find("span", class_="CallNumber")

            title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
            author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"
            availability = availability_tag.get_text(strip=True) if availability_tag else "Unknown Availability"
            call_number = call_number_tag.get_text(strip=True) if call_number_tag else "Unknown Call Number"

            book_details = f"'{title}' by {author}. {availability} Call number: {call_number}."
            books_info.append(book_details)

            # Check if the requested book is available
            if book_title.lower() in title.lower():
                return book_details

        # If no exact match, suggest alternatives
        return f"The book is not available. Here are some alternatives:\n" + "\n".join(books_info[:5])
    
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
