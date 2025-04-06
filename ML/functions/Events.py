from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup

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