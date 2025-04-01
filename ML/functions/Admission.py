from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup


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