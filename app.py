import os
# from datetime import datetime
from dotenv import load_dotenv
# import json
# import base64
# import firebase_admin
# from firebase_admin import credentials, firestore
import os
import io
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
import cloudinary
import cloudinary.uploader
from docx import Document
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai


load_dotenv()


# firebase_creds_json = base64.b64decode(os.getenv("FIREBASE_CREDENTIALS")).decode("utf-8")
# print(firebase_creds_json)
# FIREBASE_CREDENTIALS = json.loads(firebase_creds_json)
# print(FIREBASE_CREDENTIALS)
# cred = credentials.Certificate(firebase_creds)
# firebase_admin.initialize_app(cred)
# db = firestore.client()


app = Flask(__name__)
CORS(app)

genai.configure(api_key=os.getenv("GENAI_API_KEY"))
uploaded_files = {}

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


# def get_chat_history(user_id, session_id): #Done
#     """Fetch chat history from Firestore."""
#     try:
#         print("here 1")
#         session_ref = db.collection("users").document(user_id).collection("chatSessions").document(session_id)
#         session_data = session_ref.get().to_dict()
        
#         print("here 2")
#         if not session_data:
#             return []

#         messages = []
#         print("here 3")
#         for key in sorted(session_data.keys(), key=lambda k: int(k) if k.isdigit() else float("inf")):
#             if isinstance(session_data[key], dict):
#                 messages.append(session_data[key])

#         print("here 4")
#         return messages
#     except Exception as e:
#         print(f"Error fetching chat history: {e}")
#         return []
    
# def get_chat_history(user_id, session_id):
#     """Fetch chat history from Firestore."""
#     session_ref = db.collection("users").document(user_id).collection("chatSessions").document(session_id)
#     session_data = session_ref.get().to_dict()
    
#     if not session_data:
#         return []

#     messages = []
#     for key in sorted(session_data.keys(), key=lambda k: int(k) if k.isdigit() else float("inf")):
#         if isinstance(session_data[key], dict):
#             messages.append(session_data[key])

#     return messages


def generate_gemini_response(chat_history, user_message, file_uris=None): #Done
    """Send chat history and user question to Gemini API and return response."""
    try:
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
            role = "user" if msg.get("user", "").startswith("User") else "model"
            text = msg.get("text", "")
            if text:
                messages.append({"role": role, "parts": [{"text": text}]})

        # Add user message
        if user_message:
            messages.append({"role": "user", "parts": [{"text": user_message}]})

        # Attach multiple file URIs if provided
        if file_uris:
            for file_uri in file_uris:
                messages.append({"role": "user", "parts": [{"file_data": {"file_uri": file_uri}}]})

        # Generate AI response
        response = model.generate_content(messages)

        return response.text.strip() if response else "I couldn't generate a response."

    except KeyError as e:
        return f"Missing key in chat history: {str(e)}"
    except Exception as e:
        return f"Error generating AI response: {str(e)}"


def generate_markdown(file_uri=None): #Done
    """Send chat history and user question to Gemini API and return response."""
    if file_uri == "" or file_uri == None:
        return ""
    try:
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
            system_instruction="""I want you to generate a markdown on this 
            document uploaded containing the exact content"""
        )
        message = [{"role": "user", "parts": [{"file_data": {"file_uri": file_uri}}]}]
        response = model.generate_content(message)

        return response.text.strip() if response else ""
    except KeyError as e:
        return f"Missing key in chat history: {str(e)}"
    except Exception as e:
        return f"Error generating AI response: {str(e)}"
    
def generate_summary_response(user_message, file_uri=None): #Done
    """Generate a summary based on the provided message or file."""
    try:
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
            End the response with a natural and engaging closing statement that encourages further discussion or clarification while staying focused on the topic. The closing should dynamically invite the user to ask follow-up questions, explore specific points in more detail, or request clarification—without suggesting moving on to another topic."""
        )

        messages = [{"role": "user", "parts": [{"text": user_message}]}]

        if file_uri:
            messages.append({"role": "user", "parts": [{"file_data": {"file_uri": file_uri}}]})

        response = model.generate_content(messages)

        return response.text.strip() if response else "I couldn't generate a summary."

    except Exception as e:
        return f"Error generating summary: {str(e)}"


def generate_title(user_message): #Done
    """Generate a short title for the given content."""
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 4096,
                "response_mime_type": 'text/plain',
            },
            system_instruction="You are provided with the following content. Your task is to get the topic in a concise phrase."
        )

        messages = [{"role": "user", "parts": [{"text": user_message}]}]
        response = model.generate_content(messages)

        return response.text.strip() if response else "Untitled"

    except Exception as e:
        return f"Error generating title: {str(e)}"


@app.route("/api/firebase-config", methods=["GET"])
def get_firebase_config():
    """Return a safe Firebase config for the frontend (without private keys)."""

    FIREBASE_CONFIG = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
    }
    return jsonify(FIREBASE_CONFIG)

def generate_preview_image(file, ext):
    """Generate preview image from PDF, DOCX, or TXT."""
    img_buffer = io.BytesIO()

    if ext == ".pdf":
        doc = fitz.open(stream=file.read(), filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(img_buffer, format="PNG")

    elif ext == ".docx":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:
            file.save(temp_docx.name)
            document = Document(temp_docx.name)
            text = "\n".join([p.text for p in document.paragraphs][:10])
            img = text_to_image(text)
            img.save(img_buffer, format="PNG")
            os.unlink(temp_docx.name)

    elif ext == ".txt":
        text = file.read().decode("utf-8")[:1000]
        img = text_to_image(text)
        img.save(img_buffer, format="PNG")

    else:
        return None

    img_buffer.seek(0)
    upload_result = cloudinary.uploader.upload(img_buffer, folder="previews")
    return upload_result["secure_url"]

def text_to_image(text, width=800, height=600, font_size=20):
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    draw.text((10, 10), text, fill="black", font=font)
    return img

@app.route("/upload", methods=["POST"])
def upload_file():
    """Upload a file and generate a preview image if possible."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        file_type = request.form.get("file_type")
        user_id = request.form.get("user_id", "default_user")

        if not file.filename:
            return jsonify({"error": "No selected file"}), 400

        filename = os.path.join(UPLOAD_FOLDER, file.filename)
        ext = os.path.splitext(file.filename)[1].lower()

        # Save file temporarily
        file.save(filename)

        # Upload file to Gemini AI
        uploaded_file = genai.upload_file(filename)
        uploaded_files[user_id] = uploaded_file.uri

        # Generate image preview
        with open(filename, "rb") as f:
            image_preview_url = generate_preview_image(f, ext)

        # Clean up local file
        os.remove(filename)
        print(uploaded_file.uri)

        markdown = generate_markdown(uploaded_file.uri)
        if markdown == "":
            print("here")
            return jsonify({
                "message": "File uploaded successfully",
                "file_uri": uploaded_file.uri,
                "file_type": file_type,
                "imagePreviewUri": image_preview_url,
                "markdown": None
            })
        else:
            return jsonify({
                "message": "File uploaded successfully",
                "file_uri": uploaded_file.uri,
                "file_type": file_type,
                "imagePreviewUri": image_preview_url,
                "markdown": markdown
            })


    except FileNotFoundError:
        return jsonify({"error": "File path is invalid or missing"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])  # Done
def chat():
    """Handle chat messages."""
    try:
        data = request.json
        user_id = data.get("user_id")
        session_id = data.get("session_id")
        user_message = data.get("message")
        new = data.get("new", None)
        file_type = data.get("file_type", "")
        file_uris = data.get("file_uris", [])
        chat_history = data.get("chat_history", [])  # Receive chat history from frontend

        if not user_id or not session_id:
            return jsonify({"error": "Missing user_id, session_id, or message"}), 400
        
        print(user_message, file_uris)
        if user_message == "" and len(file_uris) == 0:
            return jsonify({"error": "Missing files or message"}), 400
        # Generate AI response
        try:
            ai_response = generate_gemini_response(chat_history, user_message, file_uris)
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return jsonify({"error": "Failed to generate AI response"}), 500

        if new:
            try:
                title = generate_title(ai_response)
            except Exception as e:
                print(f"Error generating title: {e}")
                title = "Untitled"
            return jsonify({"response": ai_response, "title": title, "file_type": file_type, "file_uri": file_uris})

        return jsonify({"response": ai_response, "file_type": file_type, "file_uri": file_uris})

    except Exception as e:
        print(f"Error in /chat route: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500


@app.route("/summary", methods=["POST"]) #Done
def summary():
    """Generate a summary based on user input."""
    try:
        data = request.json
        user_id = data.get("user_id")
        session_id = data.get("session_id")
        user_message = data.get("message")
        file_uri = data.get("file_uri")
        updateTimestamp = data.get("updateTimestamp")
        userTimestamp = data.get("userTimestamp")

        if not user_id or not session_id or not user_message:
            return jsonify({"error": "Missing user_id, session_id, or message"}), 400

        # Generate summary response
        ai_response = generate_summary_response(user_message, file_uri)
        title = generate_title(ai_response)

        return jsonify({"response": ai_response, "title": title, "file_uri": file_uri})

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0")
