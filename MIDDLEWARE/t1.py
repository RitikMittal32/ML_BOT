import os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()


GenAI_API_KEY = os.getenv("GenAI_API_KEY")
Pinecone_API_KEY = os.getenv("Pinecone_API_KEY")
# Configure Gemini API
genai.configure(api_key=GenAI_API_KEY)
pc = Pinecone(api_key=Pinecone_API_KEY)

# Load HuggingFace model
# model = SentenceTransformer('all-mpnet-base-v2')

# --- Setup ---

INDEX_NAME = "faculty-info"
index = pc.Index(INDEX_NAME)

# --- Search Function ---
def search(query,model):
    # 1. Embed the query
    query_embedding = model.encode([query])[0]

    # 2. Search in Pinecone
    results = index.query(
        vector=query_embedding.tolist(), 
        top_k=7, 
        include_metadata=True
    )

    # 3. Extract matched documents
    matched_texts = []
    print("🔎 Top matches:")

    for match in results.matches:
        print(f"- {match.metadata.get('filename', 'unknown file')}")
        matched_texts.append(match.metadata.get('text', ''))

    # 4. Combine top results
    combined_context = "\n\n".join(matched_texts)

    # 5. Gemini for final answer
    gemini_model = genai.GenerativeModel('gemini-1.5-pro')
    prompt = f"Based on this information: '''{combined_context}''', answer the user's question: {query}. Only give the names if asked."
    
    response = gemini_model.generate_content(prompt)
    print("\n💬 Gemini Answer:\n", response.text)
    return response.text
    

# # Example usage
# search("I want a referral for internship who can help?")
