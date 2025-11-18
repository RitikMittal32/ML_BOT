from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from google.cloud import dialogflow_v2 as dialogflow
from t1 import search
import os
import uuid
from dotenv import load_dotenv
import google.generativeai as genai
import json
from flask_cors import CORS

# Setup
app = Flask(__name__)
CORS(app)
load_dotenv()

# --- ENVIRONMENT VARIABLE LOADING ---
Service_Type = os.getenv("Service_Type")
Dialog_ProjectId = os.getenv("Dialog_ProjectId")
Dialog_PrivateId = os.getenv("Dialog_PrivateId")
Dialog_PrivateKey = os.getenv("Dialog_PrivateKey")
Dialog_ClientEmail = os.getenv("Dialog_ClientEmail")
Dialog_ClientId = os.getenv("Dialog_ClientId")
Dialog_AuthUrl = os.getenv("Dialog_AuthUrl")
Dialog_TokenUrl = os.getenv("Dialog_TokenUrl")
Dialog_AuthProvider = os.getenv("Dialog_AuthProvider")
Dialog_ClientUrl = os.getenv("Dialog_ClientUrl")
Dialog_Universe_Domain = os.getenv("Dialog_Universe_Domain")

cred_json = {
    "type": Service_Type,
    "project_id": Dialog_ProjectId,
    "private_key_id": Dialog_PrivateId,
    "private_key": Dialog_PrivateKey,
    "client_email": Dialog_ClientEmail,
    "client_id": Dialog_ClientId,
    "auth_uri": Dialog_AuthUrl,
    "token_uri": Dialog_TokenUrl,
    "auth_provider_x509_cert_url": Dialog_AuthProvider,
    "client_x509_cert_url": Dialog_ClientUrl,
    "universe_domain": Dialog_Universe_Domain
}

cred_path = "cred.json"
with open(cred_path, "w") as f:
    json.dump(cred_json, f)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

Pinecone_API_KEY = os.getenv("Pinecone_API_KEY")
pc = Pinecone(api_key=Pinecone_API_KEY)
INDEX_NAME = "intent-index"
index = pc.Index(INDEX_NAME)

model = SentenceTransformer('BAAI/bge-small-en')

INTENT_TO_REFINED_QUERY = {
    "GetLatestAnnouncement": "new events",
    "Complaint": "I have an issue",
    "SearchLibraryBooks": "Can you get the ",
    "faculty_data": " ",
    "general-lnm": " ",
    "ViewAvailableSlots": "I want to meet prof ",
    "ConfirmSlotBooking": ""
}

GenAI_API_KEY = os.getenv("GenAI_API_KEY")
genai.configure(api_key=GenAI_API_KEY)

def get_slot_params_from_gemini(query):
    gemini_model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
Analyze the user query: "{query}".
Identify and extract Faculty Name and Date.
Return a JSON object with "faculty_name" and "date" (YYYY-MM-DD).
"""
    try:
        response = gemini_model.generate_content(prompt)
        json_string = response.text.strip().strip("`").replace("\n", "")
        if json_string.startswith("json"):
            json_string = json_string[4:]
        return json.loads(json_string)
    except Exception as e:
        print(f"Error extracting slot parameters with Gemini: {e}")
        return None

def get_book_title_from_gemini(query):
    gemini_model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"Extract the book title from the following sentence and fix spelling: {query}"
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error while generating content: {e}")

def classify_intent(query, threshold=0.75):
    query_embedding = model.encode(query).tolist()
    search_result = index.query(
        vector=query_embedding,
        top_k=1,
        include_metadata=True
    )
    matches = search_result.get("matches", [])
    if matches and matches[0]["score"] >= threshold:
        return matches[0]["metadata"]["intent"]
    return None

def detect_intent_texts(project_id, session_id, text, language_code, contexts=None):
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, session_id)

    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)

    return session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )

session_contexts = {}

@app.route("/query", methods=["POST"])
def query_bot():
    data = request.get_json()
    user_message = data.get("query")
    session_id = data.get("session_id")
    project_id = "lnmiit-449207"

    predicted_intent = classify_intent(user_message)
    previous_contexts = session_contexts.get(session_id, [])

    if previous_contexts:
        refined_query = user_message
    else:
        if predicted_intent == "SearchLibraryBooks":
            refined_query = (
                INTENT_TO_REFINED_QUERY.get(predicted_intent, user_message)
                + get_book_title_from_gemini(user_message)
            )
        elif predicted_intent == "ViewAvailableSlots":
            slot_params = get_slot_params_from_gemini(user_message)
            if slot_params and slot_params.get("faculty_name") and slot_params.get("date"):
                faculty = slot_params["faculty_name"].strip()
                date = slot_params["date"].strip()
                trigger = INTENT_TO_REFINED_QUERY.get("ViewAvailableSlots", "I want to meet ")
                refined_query = f"{trigger}{faculty} on date {date}"
            else:
                refined_query = "I want to book a slot"
        elif predicted_intent in ["faculty-data", "general-lnm"]:
            refined_query = user_message
            response = search(user_message, predicted_intent)
            return jsonify({"reply": response})
        else:
            refined_query = INTENT_TO_REFINED_QUERY.get(predicted_intent, user_message)

    response = detect_intent_texts(project_id, session_id, refined_query, "en", previous_contexts)
    bot_reply = response.query_result.fulfillment_text
    session_contexts[session_id] = response.query_result.output_contexts

    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
