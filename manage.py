import os
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
# from pdf2image import convert_from_path


cred = credentials.Certificate("learnfy/secret.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
CORS(app)

genai.configure(api_key=os.environ.get("GENAI_API_KEY"))


def get_chat_history(user_id, session_id):
    """Fetch chat history from Firestore."""
    session_ref = db.collection("users").document(user_id).collection("chatSessions").document(session_id)
    session_data = session_ref.get().to_dict()
    
    if not session_data:
        return []

    messages = []
    for key in sorted(session_data.keys(), key=lambda k: int(k) if k.isdigit() else float("inf")):
        if isinstance(session_data[key], dict):  # Ensure it's a message object
            messages.append(session_data[key])

    return messages




# {
#   "user_id": "pJnMfMyFEFY1VGoUdsuySe4bnGA3",
#   "session_id": "1741663432632",
#   "message": "Explain more about circular motion."
# }

def generate_gemini_response(chat_history, user_message, file_uris=None):
    """Send chat history and user question to Gemini API and return response."""
    
    # Use the correct model name
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
            "response_mime_type": 'text/plain',
        },
        system_instruction="""In this chat, your name is 'Learnify AI'.
        Your duty is to help users understand the material they provide.
        Respond politely and ask if they need clarification.
        Make sure your answers are friendly like a teacher."""
    )

    messages = []
    
    # Process chat history
    for msg in chat_history:
        role = "user" if msg["user"].startswith("User") else "model"
        messages.append({"role": role, "parts": [{"text": msg["text"]}]})

    # Add user message
    messages.append({"role": "user", "parts": [{"text": user_message}]})

    # Attach multiple file URIs if provided
    if file_uris:
        for file_uri in file_uris:
            messages.append({"role": "user", "parts": [{"file_data": {"file_uri": file_uri}}]})

    # Generate AI response
    response = model.generate_content(messages)

    return response.text.strip() if response else "I couldn't generate a response."

def save_response_to_firestore(user_id, session_id, user_message, ai_response, updateTimestamp, userTimestamp, AITimestamp, file_uri=None, msg_type="text", title=None):
    """Append user message and AI response to Firestore without fetching existing messages."""
    session_ref = db.collection("users").document(user_id).collection("chatSessions").document(session_id)

    # Determine message type for user message
    user_message_data = {
        "text": user_message,
        "user": "User 2",
        "timestamp": userTimestamp,
        "msg_type": msg_type,
        "file_uri": file_uri if msg_type != "text" else None  # Only store file_uri if it's "doc" or "img"
    }

    # AI message (always text)
    ai_message_data = {
        "text": ai_response,
        "user": "Learnify AI",
        "timestamp": AITimestamp,
        "msg_type": "text",
        "file_uri": None  # AI response doesn't have file_uri
    }

    # Append messages using ArrayUnion
    session_ref.set({
        "messages": firestore.ArrayUnion([user_message_data, ai_message_data])  # Append new messages
    }, merge=True)

    # Set timestamp separately
    session_ref.update({"updatedAt": updateTimestamp})  
    if title:
        print("Title was set")
        session_ref.update({"name": title}) 
    else:
        session_ref.set({"name": firestore.DELETE_FIELD}, merge=True)   



uploaded_files = {}
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Ensure upload folder exists

@app.route("/upload", methods=["POST"])
def upload_file():
    """Upload a PDF file and store it for AI reference."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    file_type = request.form.get("file_type")
    user_id = request.form.get("user_id", "default_user")

    # Ensure filename is safe
    filename = os.path.join(UPLOAD_FOLDER, file.filename)

    try:
        # Save the file locally first
        file.save(filename)

        # Upload file to Gemini AI
        uploaded_file = genai.upload_file(filename)

        # Store the uploaded file URI
        uploaded_files[user_id] = uploaded_file.uri

        # Delete the temporary file
        os.remove(filename)

        return jsonify({"message": "File uploaded successfully", "file_uri": uploaded_file.uri, "file_type": file_type})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    """Handle chat messages."""
    data = request.json
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    user_message = data.get("message")
    new = data.get("new", None)
    file_type = data.get("file_type", "")
    file_uris = data.get("file_uris", [])
    print(file_uris)
    updateTimestamp = data.get("timestamp")
    userTimestamp = data.get("userTimestamp")
    if not user_id or not session_id or not user_message:
        return jsonify({"error": "Missing user_id, session_id, or message"}), 400

    # Fetch chat history
    chat_history = get_chat_history(user_id, session_id)

    # Generate AI response
    ai_response = generate_gemini_response(chat_history, user_message, file_uris)
    print(ai_response)
    AITimestamp = datetime.now().strftime("%I:%M:%S %p")

    if new:
        title = generate_title(ai_response)
        return jsonify({"response": ai_response, "title": title, "file_type": file_type, "file_uri":file_uris})
    
    return jsonify({"response": ai_response, "file_type": file_type, "file_uri":file_uris})


def generate_summary_response(user_message, file_uri=None):
    """Generate a summary based on the provided message or file."""
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 4096,
            "response_mime_type": 'text/plain',
        },
        system_instruction="""Summarize the uploaded document clearly and comprehensively, highlighting key points, important headers, and main ideas. Use bullet points where possible for readability. Ensure the summary captures all essential details while remaining concise.
End the response with a natural and engaging closing statement that encourages further discussion or clarification while staying focused on the topic. The closing should dynamically invite the user to ask follow-up questions, explore specific points in more detail, or request clarification—without suggesting moving on to another topic"""
    
    )

    messages = [{"role": "user", "parts": [{"text": user_message}]}]

    if file_uri:
        messages.append({"role": "user", "parts": [{"file_data": {"file_uri": file_uri}}]})

    response = model.generate_content(messages)

    return response.text.strip() if response else "I couldn't generate a summary."

def generate_title(user_message):
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 4096,
            "response_mime_type": 'text/plain',
        },
        system_instruction="You are provided with the following content. Your task is to get the topic in phrase.")

    messages = [{"role": "user", "parts": [{"text": user_message}]}]
    print("here I got here")
    response = model.generate_content(messages)

    return response.text.strip() if response else "I couldn't generate a summary."

@app.route("/summary", methods=["POST"])
def summary():
    """Generate a summary based on user input."""
    data = request.json
    user_id = data.get("user_id")
    session_id = data.get("session_id")
    user_message = data.get("message")
    file_uri = data.get("file_uri")
    updateTimestamp = data.get("updateTimestamp")
    userTimestamp = data.get("userTimestamp")

    if not user_id or not session_id or not user_message:
        return jsonify({"error": "Missing user_id, session_id, or message"}), 400

    # Generate summary response (no chat history)
    ai_response = generate_summary_response(user_message, file_uri)
    title = generate_title(ai_response)

    AITimestamp = datetime.now().strftime("%I:%M:%S %p")  # Format as HH:MM:SS AM/PM
    # Store response in Firestore
    # save_response_to_firestore(user_id, session_id, user_message, ai_response, updateTimestamp, userTimestamp, AITimestamp, title=title)

    return jsonify({"response": ai_response, "title": title, "file_uri":file_uri})


if __name__ == "__main__":
    app.run(debug=True)
