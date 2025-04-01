from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
import urllib3

BASE_URL = "http://172.22.2.20:8080/jspui"
SESSION = requests.Session()

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)

def get_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = SESSION.get(url, timeout=10, verify=False)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                raise

def handle_search_papers_intent(req):
    """
    Handle the SearchPapers intent and return formatted response
    Args:
        req: The Dialogflow webhook request
    Returns:
        Flask jsonify response with fulfillment messages
    """
    # Extract parameters
    paper_title = req.get('queryResult', {}).get('parameters', {}).get('paper_title', '')
    
    # Validate input
    if not paper_title:
        return jsonify({'fulfillmentText': "Please provide a paper title to search for."})
    
    print(f"Searching for paper: {paper_title}")
    
    # Get papers data
    papers = scrape_papers(paper_title)
    
    # Format response
    if not papers:
        return jsonify({
            'fulfillmentText': f"No papers found matching '{paper_title}'."
        })
    
    return format_papers_response(papers, paper_title)

def format_papers_response(papers, paper_title):
    """
    Format papers data for Dialogflow response
    Args:
        papers: List of paper dictionaries
        paper_title: Original search query
    Returns:
        Formatted jsonify response
    """
    # Create basic text response
    text_response = f"I found {len(papers)} papers about {paper_title}:\n"
    text_response += "\n".join(
        f"• {p['title']} ({p['date']}) - {p['authors']}"
        for p in papers
    )
    
    # Create rich messages
    fulfillment_messages = [
        {
            'text': {
                'text': [text_response]
            }
        }
    ]
    
    # Add cards for each paper
    for paper in papers:
        card = {
            'card': {
                'title': paper['title'],
                'subtitle': f"Published: {paper['date']} | Authors: {paper['authors']}",
                'buttons': [
                    {
                        'text': "View Paper",
                        'postback': paper['url']
                    }
                ]
            }
        }
        
        # Add download button if available
        if 'files' in paper and paper['files']:
            card['card']['buttons'].append({
                'text': "Download",
                'postback': paper['files'][0]['url']
            })
        
        fulfillment_messages.append(card)
    
    return jsonify({
        'fulfillmentText': text_response,
        'fulfillmentMessages': fulfillment_messages,
        'source': 'jspui-library-webhook'
    })

    

def scrape_papers(paper_title):
    try:
        search_url = f"{BASE_URL}/handle/123456789/8/browse"
        params = {
            'type': 'title',
            'sort_by': '1',
            'order': 'ASC',
            'rpp': '20',
            'etal': '-1',
            'starts_with': paper_title.replace(' ', '+')
        }
        
        # Try both with and without session
        try:
            response = get_with_retry(search_url, params=params)
        except:
            response = requests.get(search_url, params=params, verify=False, timeout=10)
        
        response.raise_for_status()
        logging.info(f"Response status: {response.status_code}")
        
        # Debug: Save the response content to examine
        with open('debug_response.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Alternative parsing if default fails
        results_table = soup.find("table", summary="This table browses all dspace content") or \
                       soup.find("table", class_="table") or \
                       soup.find("table")
        
        if not results_table:
            logging.error("No results table found in the page")
            return None
            
        papers = []
        for row in results_table.find_all("tr")[1:]:  # Skip header
            cols = row.find_all("td")
            if len(cols) >= 3:
                try:
                    paper = {
                        'date': cols[0].get_text(strip=True),
                        'title': cols[1].get_text(strip=True),
                        'authors': cols[2].get_text(strip=True),
                        'url': urljoin(BASE_URL, cols[1].find("a")["href"])
                    }
                    papers.append(paper)
                except Exception as e:
                    logging.error(f"Error parsing row: {str(e)}")
                    continue
        
        return papers

    except Exception as e:
        logging.error(f"Scraping error: {str(e)}")
        return None
