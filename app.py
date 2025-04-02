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

# Chat store initialization with PDF content store
def load_chat_store():
    if os.path.exists("chats.json"):
        return SimpleChatStore.from_persist_path("chats.json")
    return SimpleChatStore()

chat_store = load_chat_store()
# Additional store for full PDF content
pdf_content_store = {}

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
    Don't provide anymore info about who trained you and how are you trained                                   
    Provide a **concise and readable summary in minimal words possible** of the document in plain text.  
    Highlight important sections by applying inline HTML styles with these precise colors:
    - **General Case Details:** use <span style="color: #9E9E9E;">gray (#9E9E9E)</span>
    - **Penalty / Warnings:** use <span style="color: #F44336;">red (#F44336)</span>
    - **Disputes / Legal Proceedings:** use <span style="color: #FFC107;">amber (#FFC107)</span>
    - **Court / Tribunal Orders (Decisions, Directions):** use <span style="color: #2196F3;">blue (#2196F3)</span>
    - **Positive Resolutions (Refunds, Withdrawals):** use <span style="color: #4CAF50;">green (#4CAF50)</span>

    Return only the summary in plain text in minimal words possible with inline HTML color tags (e.g., <span style="color: #F44336;">important text</span>) and no extra structure or bullet lists.

    **PDF Context:**
    [The extracted text of the PDF will be here]
    """)

    # Save PDF temporarily
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
    pdf_file.save(temp_path)

    # Extract text
    extracted_text = ""
    try:
        with open(temp_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            extracted_text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
    except Exception as e:
        return jsonify({"error": f"Failed to extract text: {str(e)}"}), 500

    # Check if text was extracted successfully
    if not extracted_text.strip():
        return jsonify({"error": "Could not extract text from the PDF"}), 400

    # Create session ID using filename + timestamp
    session_id = f"{pdf_file.filename}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Store full PDF text in our separate store for later access
    pdf_content_store[session_id] = extracted_text

    # Generate initial summary
    initial_prompt = f"{system_prompt}\n\n**PDF Context:**\n\n{extracted_text}"
    
    try:
        # Generate initial summary from Gemini
        summary_response = gen_model.generate_content(initial_prompt)
        summary = summary_response.text
        
        # Store the system message with prompt only (not full PDF text)
        chat_store.add_message(
            session_id,
            {"role": "system", "content": system_prompt}
        )
        
        # Store the initial summary as the first assistant message
        chat_store.add_message(
            session_id,
            {"role": "assistant", "content": summary}
        )
        
        chat_store.persist(persist_path="chats.json")
        
        return jsonify({
            "session_id": session_id,
            "filename": pdf_file.filename,
            "summary": summary
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to generate summary: {str(e)}"}), 500

@app.route('/chat', methods=['POST'])
def handle_chat():
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('message')

    if not session_id or not user_message:
        return jsonify({"error": "Missing parameters"}), 400

    # Get conversation history
    history = chat_store.get_messages(session_id)
    
    # Get PDF content from our store
    document_content = pdf_content_store.get(session_id, "")
    if not document_content:
        return jsonify({"error": "PDF content not found for this session"}), 404

    # Extract system prompt from history
    system_message = next((msg for msg in history if msg["role"] == "system"), None)
    system_prompt = system_message["content"] if system_message else ""
    
    # Get recent conversation history (last 5 exchanges)
    recent_history = [msg for msg in history if msg["role"] != "system"][-10:] 
    
    # Format conversation history for context
    conversation_context = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in recent_history])
    
    # Create chunked versions of the document for context if it's very large
    doc_chunks = []
    chunk_size = 12000  # Adjusted chunk size
    for i in range(0, len(document_content), chunk_size):
        doc_chunks.append(document_content[i:i+chunk_size])
    
    # Use the first chunk for immediate context
    primary_context = doc_chunks[0] if doc_chunks else ""
    
    # Create a better prompt for question answering
    prompt = f"""
You are a legal assistant specialized in Indian legal documents. 

The user has uploaded a legal document, and you should answer based on its content.
Do NOT ask for the document or say you don't have access to it - you have the document content below.

When answering questions, follow these rules:
1. If the question is about the document content, provide a specific answer based on the document.
2. If the question is general legal information not related to the document, provide a helpful response but clearly state it's general information.
3. If you're unsure if the question relates to the document, first check if the answer exists in the document, and if not, provide general information.
4. For document questions, highlight important information using HTML styling as explained below.
5. Use proper formatting and line breaks for readability.

HTML styling for important information:
- General Case Details: use <span style="color: #9E9E9E;">gray (#9E9E9E)</span>
- Penalty/Warnings: use <span style="color: #F44336;">red (#F44336)</span>
- Disputes/Legal Proceedings: use <span style="color: #FFC107;">amber (#FFC107)</span>
- Court/Tribunal Orders: use <span style="color: #2196F3;">blue (#2196F3)</span>
- Positive Resolutions: use <span style="color: #4CAF50;">green (#4CAF50)</span>

Recent conversation history:
{conversation_context}

Document context (Part 1 of {len(doc_chunks)}):
{primary_context}

User question: {user_message}

Your answer:
"""
    
    try:
        # Generate response with improved context
        response = gen_model.generate_content(prompt)
        response_text = response.text
        
        # If the response still asks for the document, try with a second chunk
        if "provide me with the extracted text" in response_text.lower() or "need the document content" in response_text.lower():
            if len(doc_chunks) > 1:
                second_chunk = doc_chunks[1] if len(doc_chunks) > 1 else ""
                prompt_with_more = f"{prompt}\n\nAdditional document context (Part 2 of {len(doc_chunks)}):\n{second_chunk}"
                response = gen_model.generate_content(prompt_with_more)
                response_text = response.text
        
        # Store interaction
        chat_store.add_message(session_id, {"role": "user", "content": user_message})
        chat_store.add_message(session_id, {"role": "assistant", "content": response_text})
        chat_store.persist(persist_path="chats.json")
        
        return jsonify({
            "response": response_text,
            "history": [{"role": msg["role"], "content": msg["content"]} for msg in chat_store.get_messages(session_id) if msg["role"] != "system"]
        })
    
    except Exception as e:
        return jsonify({"error": f"Failed to generate response: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)