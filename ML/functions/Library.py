from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote



def get_book_list(book_title):
    """
    For PARENT INTENT - Searches for multiple books and returns a formatted list
    Returns either:
    - Direct details if single book found (by calling get_single_book_details)
    - List of matching books if multiple found
    - Error message if none found
    """
        # First clean the title
    cleaned_title = book_title.strip()
    
    # Replace specific punctuation that might affect searches
    replacements = {
        ',': '%2C',
        "'": '%27',
        '"': '%22',
        '!': '%21',
        '?': '%3F',
        ':': '%3A',
        ';': '%3B',
        '(': '%28',
        ')': '%29',
        '&': '%26'
    }
    
    # Apply replacements
    for char, code in replacements.items():
        cleaned_title = cleaned_title.replace(char, code)
    
    # Replace spaces with +
    book_title_query = cleaned_title.replace(' ', '+')
    search_url = f"https://lnmiit-opac.kohacloud.in/cgi-bin/koha/opac-search.pl?idx=&limit=&q={book_title_query}&limit=&weight_search=1"

    try:
        response = requests.get(search_url, verify=False, timeout=10)
        if response.status_code != 200:
            return f"Error: Failed to access library catalog (Status {response.status_code})"

        soup = BeautifulSoup(response.content, "html.parser")

        # First check for single book result
        single_book = soup.find("div", class_="record")
        if single_book:
            return get_book_info(soup)  # Delegate to single book handler

        # Process multiple books case
        results_table = soup.find("table", class_="table table-striped")
        if not results_table:
            return "No books found matching your search."

        rows = results_table.find_all("tr") # Skip header row
        if not rows:
            return "The search returned no results."

        books = []
        for row in rows:
            title_tag = row.find("a", class_="title")
            if not title_tag:
                continue
                
            title = title_tag.get_text(strip=True)
            author_tag = row.find("ul", class_="author")
            author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"

            # Get biblionumber from the checkbox input
            biblio_input = row.find("input", class_="cb")
            biblionumber = biblio_input["value"] if biblio_input else None
            
            books.append({
                'title': title,
                'author': author,
                'biblionumber': biblionumber, 
                'full_row': row  # Pass entire row for detailed processing if needed
            })

        if not books:
            return "No matching books found."
            
        partial_matches = [b for b in books if book_title.lower() in b['title'].lower()]
        if partial_matches:
            return format_book_list(partial_matches, "Matches found:")
            
        return format_book_list(books, "All books in search results")

    except Exception as e:
        print(f"Search error: {e}")
        return "Error searching the library catalog"

def get_single_book_details(book_title):
    """
    For FOLLOW-UP INTENT - Extracts detailed information about a specific book
    Returns formatted string with complete book details
    """
    # First clean the title
    cleaned_title = book_title.strip()
    
    # Replace specific punctuation that might affect searches
    replacements = {
        ',': '%2C',
        "'": '%27',
        '"': '%22',
        '!': '%21',
        '?': '%3F',
        ':': '%3A',
        ';': '%3B',
        '(': '%28',
        ')': '%29',
        '&': '%26'
    }
    
    # Apply replacements
    for char, code in replacements.items():
        cleaned_title = cleaned_title.replace(char, code)
    
    # Replace spaces with +
    book_title_query = cleaned_title.replace(' ', '+')
    search_url = f"https://lnmiit-opac.kohacloud.in/cgi-bin/koha/opac-search.pl?idx=&limit=&q={book_title_query}&limit=&weight_search=1"

    try:
        response = requests.get(search_url, verify=False, timeout=10)
        if response.status_code != 200:
            return f"Error: Failed to access library catalog (Status {response.status_code})"
        soup = BeautifulSoup(response.content, "html.parser")
        return get_book_info(soup)

    except Exception as e:
        print(f"Detail extraction error: {e}")
        return "Could not retrieve complete book details"
    
def get_single_book_bibilo(book_title, biblo_num):
    """
    For FOLLOW-UP INTENT - Extracts detailed information about a specific book
    Returns formatted string with complete book details
    """
    encoded_title = quote(book_title)
   # Construct the URL
    search_url = f"https://lnmiit-opac.kohacloud.in/cgi-bin/koha/opac-detail.pl?biblionumber={biblo_num}&query_desc=kw%2Cwrdl%3A{encoded_title}"

    try:
        response = requests.get(search_url, verify=False, timeout=10)
        if response.status_code != 200:
            return f"Error: Failed to access library catalog (Status {response.status_code})"

        soup = BeautifulSoup(response.content, "html.parser")
        return get_book_info(soup)

    except Exception as e:
        print(f"Detail extraction error: {e}")
        return "Could not retrieve complete book details"
    

def get_book_info(soup):
    """
    Extracts book details from a BeautifulSoup object and returns formatted information.
    
    Args:
        soup (BeautifulSoup): BeautifulSoup object containing the book details page
    
    Returns:
        str: Formatted string containing book details or error message
    """
    record = soup.find("div", class_="record")
    if not record:
        return "Book details not available"

    try:
        # Extract basic information
        title = record.find("h1", class_="title").text.strip() if record.find("h1", class_="title") else "Unknown Title"
        author_tag = record.find("span", property="name")
        author = author_tag.text.strip() if author_tag else "Unknown Author"
        
        # Extract ISBN
        isbn_tag = record.find("span", property="isbn")
        isbn = isbn_tag.text.strip() if isbn_tag else "Unknown ISBN"
        
        # Extract publication details (not present in sample, keeping as fallback)
        publication = "Unknown Publication"
        
        # Extract call number from holdings table
        call_number_tag = soup.find("td", class_="call_no")
        call_number = call_number_tag.text.strip() if call_number_tag else "Unknown Call Number"
        
        # Extract availability information
        availability = []
        holdings_table = soup.find("table", id="holdingst")
        if holdings_table:
            availability = []
            any_available = False  # Flag to track if any book is available
            
            for row in holdings_table.find_all("tr")[1:]:  # Skip header row
                cols = row.find_all("td")
                if len(cols) >= 7:  # Ensure we have all columns
                    status_cell = cols[3]  # Status column
                    
                    # Check for available status in two ways:
                    # 1. Look for <span class="item-status available">
                    # 2. Look for <link property="availability" href="http://schema.org/InStock">
                    available_span = status_cell.find('span', class_='item-status available')
                    in_stock_link = status_cell.find('link', {'property': 'availability', 'href': 'http://schema.org/InStock'})
                    
                    if available_span and "Available" in available_span.get_text(strip=True):
                        any_available = True
                        break
            
            # Final availability status
            availability_status = "Available" if any_available else "Not available"
            availability.append(availability_status)
        # Extract holds information
        holds_tag = soup.find("div", id="bib_holds")
        holds = holds_tag.text.strip() if holds_tag else "No holds information"
        
        # Format the complete response
        details = [
            f"Title: {title}",
            f"Author: {author}",
            f"ISBN: {isbn}",
            f"Publication: {publication}",
            f"Call Number: {call_number}",
            "\nAvailability:",
            *(availability if availability else ["No availability information"]),
            f"\nHolds Information: {holds}"
        ]
        
        return "\n".join(details)
        
    except Exception as e:
        print(f"Error extracting details: {str(e)}")
        return "Could not retrieve complete book details"

def format_book_list(books, header):
    """Helper function to format book lists consistently with biblionumber"""
    return (
        f"{header}:\n\n" +
        "\n".join(
            f"{i+1}. {b['title']} by {b['author']} (Biblionumber: {b['biblionumber']})" 
            for i, b in enumerate(books)
        ) +
        "\n\nPlease specify which book you want (e.g. 'title')" +
        "\n\n Note -: If multiple book with same title found write ''title' with 'biblionumber''."

    )
