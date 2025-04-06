from flask import Flask, jsonify
import requests
from bs4 import BeautifulSoup
import json
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from fuzzywuzzy import fuzz

# Disable SSL warnings (not recommended for production)
urllib3.disable_warnings(InsecureRequestWarning)

app = Flask(__name__)

def safe_find(parent, element_type=None, **kwargs):
    """Safely find an element, returning None if not found"""
    if parent is None:
        return None
    try:
        if element_type is None:
            return parent.find(**kwargs)
        return parent.find(element_type, **kwargs)
    except:
        return None

def safe_find_all(parent, element_type=None, **kwargs):
    """Safely find all elements, returning empty list if not found"""
    if parent is None:
        return []
    try:
        if element_type is None:
            return parent.find_all(**kwargs)
        return parent.find_all(element_type, **kwargs)
    except:
        return []

def safe_find_next(parent, element_type=None, **kwargs):
    """Safely find next element, returning None if not found"""
    if parent is None:
        return None
    try:
        if element_type is None:
            return parent.find_next(**kwargs)
        return parent.find_next(element_type, **kwargs)
    except:
        return None

def extract_scholarships_assistantships(soup):
    scholarship_data = {
        "Introduction": "",
        "Scholarships": {},
        "Assistantships": {},
        "External_Scholarships": []
    }

    # 1. Introduction Section
    intro_container = safe_find(soup, 'div', attrs={'data-id': '762364c'})
    if intro_container:
        intro_text = safe_find(intro_container, 'p')
        if intro_text:
            scholarship_data["Introduction"] = intro_text.get_text(strip=True)

    # 2. Scholarships (A- Scholarships)
    scholarships_container = safe_find(soup, 'div', attrs={'data-id': '164823b'})
    if scholarships_container:
        tabs = safe_find(scholarships_container, 'div', class_='e-n-tabs-content')
        if tabs:
            scholarship_types = safe_find_all(tabs, 'div', class_='e-n-tab-content')
            for tab in scholarship_types:
                title = safe_find(tab, 'h3')
                if title:
                    title_text = title.get_text(strip=True).replace(':', '')
                    content = {
                        "description": "",
                        "eligibility": {},
                        "amount": ""
                    }
                    
                    # Extract description
                    description = safe_find(tab, 'p')
                    if description:
                        content["description"] = description.get_text(strip=True)
                    
                    # Extract eligibility criteria
                    h4_tags = safe_find_all(tab, 'h4')
                    for h4 in h4_tags:
                        section = h4.get_text(strip=True).replace(':', '')
                        next_p = h4.find_next('p')
                        next_ul = h4.find_next('ul')
                        
                        if next_p and (not next_ul or next_p.find_next() == next_ul):
                            content["eligibility"][section] = next_p.get_text(strip=True)
                        if next_ul:
                            content["eligibility"][section] = [
                                li.get_text(strip=True) for li in safe_find_all(next_ul, 'li')
                            ]
                    
                    # Extract amount if mentioned in description
                    if "amount" in content["description"].lower():
                        amount = content["description"].split("amount is")[-1].split(".")[0].strip()
                        content["amount"] = amount
                    
                    scholarship_data["Scholarships"][title_text] = content

    # 3. Assistantships (B- Assistantships)
    assistantships_container = safe_find(soup, 'div', attrs={'data-id': '3b0ea85'})
    if assistantships_container:
        tabs = safe_find(assistantships_container, 'div', class_='e-n-tabs-content')
        if tabs:
            assistantship_types = safe_find_all(tabs, 'div', class_='e-n-tab-content')
            for tab in assistantship_types:
                title = safe_find(tab, 'h3')
                if title:
                    title_text = title.get_text(strip=True).replace(':', '')
                    content = {
                        "description": "",
                        "eligibility": {},
                        "amount": "",
                        "conditions": []
                    }
                    
                    # Extract description and amount
                    paragraphs = safe_find_all(tab, 'p')
                    if paragraphs:
                        content["description"] = paragraphs[0].get_text(strip=True)
                        if "amount" in content["description"].lower():
                            amount = content["description"].split("amount is")[-1].split(".")[0].strip()
                            content["amount"] = amount
                    
                    # Extract eligibility and conditions
                    h4_tags = safe_find_all(tab, 'h4')
                    for h4 in h4_tags:
                        section = h4.get_text(strip=True).replace(':', '')
                        next_p = h4.find_next('p')
                        next_ul = h4.find_next('ul')
                        
                        if next_p and (not next_ul or next_p.find_next() == next_ul):
                            content["eligibility"][section] = next_p.get_text(strip=True)
                        if next_ul:
                            items = [li.get_text(strip=True) for li in safe_find_all(next_ul, 'li')]
                            if "condition" in section.lower() or "note" in section.lower():
                                content["conditions"].extend(items)
                            else:
                                content["eligibility"][section] = items
                    
                    # Extract any additional notes
                    notes = safe_find(tab, 'ul', class_='genul')
                    if notes:
                        content["conditions"].extend(
                            [li.get_text(strip=True) for li in safe_find_all(notes, 'li')]
                        )
                    
                    scholarship_data["Assistantships"][title_text] = content

    # 4. External Scholarships
    external_container = safe_find(soup, 'div', attrs={'data-id': '8e58516'})
    if external_container:
        table = safe_find(external_container, 'table', class_='table-bordered')
        if table:
            rows = safe_find_all(table, 'tr')
            for row in rows:
                cols = safe_find_all(row, 'td')
                if cols and len(cols) >= 2:
                    scholarship_data["External_Scholarships"].append({
                        "name": cols[0].get_text(strip=True),
                        "provider": cols[1].get_text(strip=True)
                    })

    return scholarship_data

def extract_table_data(table):
    """Extract data from a table into a list of dictionaries"""
    if not table:
        return []
    
    rows = safe_find_all(table, 'tr')
    if not rows:
        return []
    
    headers = [th.get_text(strip=True) for th in safe_find_all(rows[0], 'th') or []]
    data = []
    
    for row in rows:  # Skip header row
        cols = safe_find_all(row, 'td')
        if cols:
            row_data = {}
            for i, col in enumerate(cols):
                header = headers[i] if i < len(headers) else f"Column_{i}"
                row_data[header] = col.get_text(strip=True)
            data.append(row_data)
    
    return data

def extract_important_dates(soup):
    dates_heading = safe_find(soup, lambda tag: tag.name in ['h2', 'h3'] and 
                              'important dates' in tag.get_text().lower())
    dates_table = safe_find_next(dates_heading, 'table') if dates_heading else None
    table_data = extract_table_data(dates_table)
    if not table_data:
        return "Important Dates section not found"
    
    # Format as two-column table
    output = ["Important Dates:", "----------------"]
    for row in table_data:
        if isinstance(row, dict) and 'Column_0' in row and 'Column_1' in row:
            output.append(f"{row['Column_0']}: {row['Column_1']}")
        elif isinstance(row, str):
            output.append(row)
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            output.append(f"{row[0]}: {row[1]}")
    
    return "\n".join(output)

def extract_programmes_offered(soup):
    programmes_heading = safe_find(soup, lambda tag: tag.name in ['h2', 'h3'] and 
                                   'programmes offered' in tag.get_text().lower())
    if not programmes_heading:
        return "Programmes Offered section not found"
    
    # Find the table-responsive div and extract table data
    programmes_div = safe_find_next(programmes_heading, 'div', class_='table-responsive')
    programmes_table = safe_find(programmes_div, 'table') if programmes_div else None
    table_data = extract_table_data(programmes_table) if programmes_table else []
    
    # Extract notes section
    notes_heading = safe_find_next(programmes_heading, 'h3', string='Note :')
    notes_list = safe_find_next(notes_heading, 'ul') if notes_heading else None
    notes_items = [li.get_text(strip=True) for li in safe_find_all(notes_list, 'li')] if notes_list else []
    
    # Format the output
    output = ["Programmes Offered:", "-------------------"]
    current_seats = ""
    
    for row in safe_find_all(programmes_table, 'tr'):
        cells = safe_find_all(row, 'td')
        if len(cells) >= 2:
            programme = cells[0].get_text(strip=True)
            seats = cells[1].get_text(strip=True)
            
            if seats:  # If seats cell is not empty
                current_seats = seats
                output.append(f"{programme}:{current_seats}")
            else:  # If seats cell is empty (rowspan case)
                output.append(f"{programme}")
        elif len(cells) == 1:  # For single cell rows (shouldn't happen in this table)
            programme = cells[0].get_text(strip=True)
            output.append(f"{programme}")
    
    # Add notes section if exists
    if notes_items:
        output.append("\nNotes:")
        output.extend(f"• {note}" for note in notes_items)
    
    return "\n".join(output) if output else "No programme information found"

def extract_eligibility_criteria(soup):
    eligibility_container = safe_find(soup, 'div', attrs={'data-id': '6b1558f'})
    if not eligibility_container:
        return "Eligibility Criteria section not found"
    eligibility_widget = safe_find(eligibility_container, 'div', class_='elementor-widget-text-editor')
    if not eligibility_widget:
        return "Eligibility Criteria content not found"
    eligibility_list = safe_find(eligibility_widget, 'ul', class_='genul')
    if not eligibility_list:
        return "Eligibility Criteria list not found"
    items = [li.get_text(strip=True) for li in safe_find_all(eligibility_list, 'li')]
    return "Eligibility Criteria:\n\n" + "\n".join(f"• {item}" for item in items)

def extract_instructions_to_apply(soup):
    instructions_container = safe_find(soup, 'div', attrs={'data-id': '617fd93'})
    if not instructions_container:
        return "Instructions to Apply section not found"
    instructions_widget = safe_find(instructions_container, 'div', class_='elementor-widget-text-editor')
    if not instructions_widget:
        return "Instructions to Apply content not found"
    instructions_list = safe_find(instructions_widget, 'ul', class_='genul')
    if not instructions_list:
        return "Instructions to Apply list not found"
    items = [li.get_text(strip=True) for li in safe_find_all(instructions_list, 'li')]
    return "Instructions to Apply:\n\n" + "\n".join(f"• {item}" for item in items)

def extract_merit_list_preparation(soup):
    merit_container = safe_find(soup, 'div', attrs={'data-id': '4c6c62e'})
    if not merit_container:
        return "Merit List Preparation section not found"
    merit_widget = safe_find(merit_container, 'div', class_='elementor-widget-text-editor')
    if not merit_widget:
        return "Merit List Preparation content not found"
    merit_list = safe_find(merit_widget, 'ul', class_='genul')
    if not merit_list:
        return "Merit List Preparation list not found"
    
    output = ["Merit List Preparation:"]
    for li in safe_find_all(merit_list, 'li', recursive=False):
        item = li.get_text(strip=True)
        nested_ul = safe_find(li, 'ul', class_='genul')
        if nested_ul:
            output.append(f"\n• {item.split('.')[0]}:")
            for nested_li in safe_find_all(nested_ul, 'li'):
                output.append(f"  - {nested_li.get_text(strip=True)}")
        else:
            output.append(f"• {item}")
    return "\n".join(output)

def extract_counseling_process(soup):
    counseling_container = safe_find(soup, 'div', attrs={'data-id': 'fc3ec32'})
    if not counseling_container:
        return "Counseling Process section not found"
    counseling_widget = safe_find(counseling_container, 'div', class_='elementor-widget-text-editor')
    if not counseling_widget:
        return "Counseling Process content not found"
    counseling_list = safe_find(counseling_widget, 'ul', class_='genul')
    if not counseling_list:
        return "Counseling Process list not found"
    items = [li.get_text(strip=True).replace('\xa0', ' ') for li in safe_find_all(counseling_list, 'li')]
    return "Counseling Process:\n\n" + "\n".join(f"• {item}" for item in items)

def extract_fee_structure(soup):    
    fee_container = safe_find(soup, 'div', attrs={'data-id': '7445779'})
    if not fee_container:
        return "Fee Structure section not found"
    
    fee_widget = safe_find(fee_container, 'div', class_='elementor-widget-text-editor')
    if not fee_widget:
        return "Fee Structure content not found"
    
    output = ["Fee Structure:", "---------------"]
    
    # Extract B.Tech Programme fees
    btech_header = safe_find(fee_widget, 'p', string=lambda t: 'B.Tech Programme' in t)
    if btech_header:
        btech_table = safe_find_next(btech_header, 'table')
        if btech_table:
            output.append("\nB.Tech Programme (per semester):")
            current_main_item = None
            
            for row in safe_find_all(btech_table, 'tr'):
                cells = safe_find_all(row, 'td')
                if len(cells) == 3:
                    code = cells[0].get_text(strip=True)
                    desc = cells[1].get_text(strip=True)
                    amount = cells[2].get_text(strip=True)
                    
                    if code and desc and amount:
                        if code in ['A', 'B']:  # Main items
                            current_main_item = f"{code}. {desc}"
                            output.append(f"  {current_main_item}: ₹{amount}" if amount.strip() else f"  {current_main_item}")
                        else:  # Sub-items
                            if 'ul' in str(cells[1]):  # Has bullet points
                                bullet_items = [li.get_text(strip=True) for li in safe_find_all(cells[1], 'li')]
                                for item in bullet_items:
                                    output.append(f"    • {item}: ₹{amount}")
                            else:
                                output.append(f"    • {desc}: ₹{amount}")
                    elif code == '' and desc == '' and amount:  # Total row
                        output.append(f"    • Total: ₹{amount}")

    # Extract B.Sc - M.Sc Programme fees
    bsc_header = safe_find(fee_widget, 'p', string=lambda t: 'B.Sc – M.Sc' in t)
    if bsc_header:
        bsc_table = safe_find_next(bsc_header, 'table')
        if bsc_table:
            output.append("\nB.Sc - M.Sc Programme (per semester):")
            current_main_item = None
            
            for row in safe_find_all(bsc_table, 'tr'):
                cells = safe_find_all(row, 'td')
                if len(cells) == 3:
                    code = cells[0].get_text(strip=True)
                    desc = cells[1].get_text(strip=True)
                    amount = cells[2].get_text(strip=True)
                    
                    if code and desc and amount:
                        if code in ['A', 'B']:  # Main items
                            current_main_item = f"{code}. {desc}"
                            output.append(f"  {current_main_item}: ₹{amount}" if amount.strip() else f"  {current_main_item}")
                        else:  # Sub-items
                            if 'ul' in str(cells[1]):  # Has bullet points
                                bullet_items = [li.get_text(strip=True) for li in safe_find_all(cells[1], 'li')]
                                for item in bullet_items:
                                    output.append(f"    • {item}: ₹{amount}")
                            else:
                                output.append(f"    • {desc}: ₹{amount}")
                    elif code == '' and desc == '' and amount:  # Total row
                        output.append(f"    • Total: ₹{amount}")

    # Extract Hostel and Mess charges
    hostel_header = safe_find(fee_widget, 'p', string=lambda t: 'Hostel and Mess' in t)
    if hostel_header:
        hostel_table = safe_find_next(hostel_header, 'table')
        if hostel_table:
            output.append("\nHostel and Mess Charges (per semester):")
            for row in safe_find_all(hostel_table, 'tr'):
                cells = safe_find_all(row, 'td')
                if len(cells) == 2:
                    desc = cells[0].get_text(strip=True)
                    amount = cells[1].get_text(strip=True)
                    if desc and amount:
                        if "TOTAL" in desc:
                            output.append(f"  {desc}: ₹{amount}")
                        else:
                            output.append(f"  • {desc}: ₹{amount}")
    
    # Extract notes
    notes = []
    note_paragraphs = safe_find_all(fee_widget, 'p')
    for p in note_paragraphs:
        text = p.get_text(strip=True)
        if '**' in text or 'NOTE:' in text:
            notes.append(text.replace('**', '').strip())
    
    note_items = [li.get_text(strip=True) for li in safe_find_all(fee_widget, 'li')]
    notes.extend(note_items)
    
    if notes:
        output.append("\nNotes:")
        for note in notes:
            if note.startswith("•"):
                output.append(f"  {note}")
            else:
                output.append(f"  • {note}")
    
    return "\n".join(output)

def extract_refund_policy(soup):
    refund_container = safe_find(soup, 'div', attrs={'data-id': 'e7628df'})
    if not refund_container:
        return "Refund Policy section not found"
    refund_button = safe_find(refund_container, 'a', class_='elementor-button-link')
    if not refund_button:
        return "Refund Policy link not found"
    return f"Refund Policy:\n\n• {refund_button.get_text(strip=True)}\n• Link: {refund_button['href']}"

def extract_contact_information(soup):
    contact_container = safe_find(soup, 'div', attrs={'data-id': '7ca2485'})
    if not contact_container:
        return "Contact Information section not found"
    contact_widget = safe_find(contact_container, 'div', class_='elementor-widget-text-editor')
    if not contact_widget:
        return "Contact Information content not found"
    
    output = ["Contact Information:"]
    for p in safe_find_all(contact_widget, 'p'):
        text = p.get_text(strip=True).replace('\xa0', ' ')
        if text.startswith("Postal address:"):
            output.append(f"• Postal Address: {text.split('Postal address:')[1].strip()}")
        elif text.startswith("Contact No. (Toll Free):"):
            output.append(f"• Toll Free Number: {text.split('Contact No. (Toll Free):')[1].strip()}")
        elif text.startswith("Contact No. (Direct):"):
            output.append(f"• Direct Numbers: {text.split('Contact No. (Direct):')[1].strip()}")
        elif text.startswith("E-mail Id:"):
            output.append(f"• Email: {text.split('E-mail Id:')[1].strip()}")
    
    if len(output) == 1:  # Only header was added
        return "No contact information found"
    
    return "\n".join(output)


def format_admission_sections(admission_data, header=None):
    """Format admission sections as plain text only"""
    if not admission_data:
        return "No admission information available."
    
    if header:  # Single section response
        section_data = admission_data.get(header, {})
        if isinstance(section_data, str):
            return f"{header}:\n\n{section_data}"
        elif isinstance(section_data, list):
            return f"{header}:\n\n" + "\n".join(f"• {item}" for item in section_data)
        elif isinstance(section_data, dict):
            return f"{header}:\n\n" + "\n".join(f"• {k}: {v}" for k, v in section_data.items())
        return f"{header} information is not in expected format."
    else:  # All sections response
        return (
            "Available Admission Information Sections:\n\n" +
            "\n".join(f"• {section}" for section in admission_data.keys()) +
            "\n\nPlease specify which section you want (e.g. 'Important Dates')" +
            "\n\nType 'exit' to cancel."
        )


def scrape_admission_details(user_title=None):
    url = "https://lnmiit.ac.in/admissions/ug/regular-mode/"
    try:
        # headers = {
        #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        # }
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        admission_data = {}

        # Mapping of section titles to their respective extraction functions
        section_functions = {
            "Important Dates": extract_important_dates,
            "Programmes Offered": extract_programmes_offered,
            "Eligibility Criteria": extract_eligibility_criteria,
            "Instructions to Apply": extract_instructions_to_apply,
            "Merit List Preparation": extract_merit_list_preparation,
            "Counseling Process": extract_counseling_process,
            "Fee Structure": extract_fee_structure,
            "Refund Policy": extract_refund_policy,
            "Scholarships & Assistantships": extract_scholarships_assistantships,
            "Contact Information": extract_contact_information
        }

        if user_title:
            # Use fuzzy matching to find the closest section title
            best_match = None
            highest_score = 0
            threshold = 80  # Adjust this threshold as needed

            for section_title in section_functions.keys():
                score = fuzz.ratio(user_title.lower(), section_title.lower())
                if score > highest_score and score >= threshold:
                    highest_score = score
                    best_match = section_title

            if best_match:
                admission_data[best_match] = section_functions[best_match](soup)
                return format_admission_sections(admission_data, best_match)
            else:
                available = list(section_functions.keys())
                return (
                    f"No matching section found for '{user_title}'.\n\n" +
                    "Available sections:\n" +
                    "\n".join(f"• {section}" for section in available) +
                    "\n\nPlease try again or type 'exit' to cancel."
                )
        else:
            # If no title is provided, run all extraction functions
            for section_title, extraction_function in section_functions.items():
                admission_data[section_title] = extraction_function(soup)

        return admission_data
    except requests.RequestException as e:
        return f"Failed to retrieve admission information. Please try again later. {str(e)}"
    except Exception as e:
        return f"An error occurred while processing admission information. {str(e)}"



