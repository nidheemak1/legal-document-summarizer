import re
from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
from llama_index.core.storage.chat_store import SimpleChatStore
import os
import tempfile
import PyPDF2
from datetime import datetime
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import fitz  # PyMuPDF

# Load pre-trained Legal-BERT model
tokenizer = AutoTokenizer.from_pretrained("nlpaueb/legal-bert-base-uncased")
model = AutoModelForSequenceClassification.from_pretrained("nlpaueb/legal-bert-base-uncased")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gen_model = genai.GenerativeModel('gemini-1.5-flash')

# Chat store initialization
def load_chat_store():
    if os.path.exists("chats.json"):
        return SimpleChatStore.from_persist_path("chats.json")
    return SimpleChatStore()

chat_store = load_chat_store()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'pdf' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    # Enhanced system prompt with better formatting instructions
    system_prompt = request.form.get('system_prompt', """
    You are a legal assistant specialized in Indian legal documents.  
    Provide a **concise and readable summary** of the document in plain text.  
    Highlight important sections by applying inline HTML styles with these precise colors:
    - **General Case Details:** use <span style="color: #9E9E9E;">gray (#9E9E9E)</span>
    - **Penalty / Warnings:** use <span style="color: #F44336;">red (#F44336)</span>
    - **Disputes / Legal Proceedings:** use <span style="color: #FFC107;">amber (#FFC107)</span>
    - **Court / Tribunal Orders (Decisions, Directions):** use <span style="color: #2196F3;">blue (#2196F3)</span>
    - **Positive Resolutions (Refunds, Withdrawals):** use <span style="color: #4CAF50;">green (#4CAF50)</span>

    Return only the summary in plain text with inline HTML color tags (e.g., <span style="color: #F44336;">important text</span>) and no extra structure or bullet lists.

    **PDF Context:**
    [The extracted text of the PDF will be here]
    """)


    # Save PDF temporarily
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
    pdf_file.save(temp_path)

    # Extract text
    with open(temp_path, "rb") as f:
        pdf_reader = PyPDF2.PdfReader(f)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])

    # Create session ID using filename + timestamp
    session_id = f"{pdf_file.filename}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Store PDF text as system message
    chat_store.add_message(
        session_id,
        {"role": "system", "content": f"{system_prompt}\n\n**PDF Context:**\n\n{text}"}
    )
    chat_store.persist(persist_path="chats.json")

    return jsonify({
        "session_id": session_id,
        "filename": pdf_file.filename
    })

@app.route('/chat', methods=['POST'])
def handle_chat():
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('message')

    if not session_id or not user_message:
        return jsonify({"error": "Missing parameters"}), 400

    # Get conversation history
    history = chat_store.get_messages(session_id)

    # Extract system prompt and context from history
    system_context = next((msg["content"] for msg in history if msg["role"] == "system"), "You are a legal assistant helping analyze legal documents.")
    
    # Generate response with context
    prompt = f"{system_context}\n\nUser Question: {user_message}\n\nAssistant Answer (use proper Markdown with line breaks between each item):"
    response = gen_model.generate_content(prompt)

    # Keep the Markdown formatting intact
    response_text = response.text
    print(response_text)
    # Store interaction
    chat_store.add_message(session_id, {"role": "user", "content": user_message})
    chat_store.add_message(session_id, {"role": "assistant", "content": response_text})
    chat_store.persist(persist_path="chats.json")

    return jsonify({
        "response": response_text,
        "history": [{"role": msg["role"], "content": msg["content"]} for msg in chat_store.get_messages(session_id)[1:]]
    })

if __name__ == '__main__':
    app.run(debug=True)