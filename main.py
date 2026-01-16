import os
import re
import shutil
import uuid
import json
import base64
import requests
from typing import List, Dict, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import PyPDF2
import io


# Force load .env from current directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

MURF_API_KEY = os.getenv("MURF_API_KEY")
print(f"Loading .env from: {env_path}")
print(f"MURF_API_KEY loaded: {'Yes' if MURF_API_KEY else 'No'}")
print(f"Key Length: {len(MURF_API_KEY) if MURF_API_KEY else 0}")


app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Directories
UPLOAD_DIR = "uploads"
AUDIO_DIR = "generated_audio"
STATIC_DIR = "static"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"

# Serve the UI
@app.get("/")
async def read_root():
    return FileResponse(os.path.join(STATIC_DIR, 'index.html'))

# Voice Configuration
# Mapping user-friendly names to specific Murf Voice IDs.
# These IDs should be verified. If they are invalid, the user needs to update them.
# Voice Configuration
# We will fetch voices dynamically to ensure they are valid.
CACHED_VOICES = []

def fetch_murf_voices():
    if not MURF_API_KEY:
        print("Cannot fetch voices: API Key not set.")
        return []
        
    try:
        headers = {"api-key": MURF_API_KEY, "Accept": "application/json"}
        response = requests.get("https://api.murf.ai/v1/speech/voices", headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"Failed to fetch voices: {response.status_code}")
        return []
    except Exception as e:
        print(f"Error fetching voices: {e}")
        return []

def get_voice_by_criteria(all_voices, locale, gender):
    """Finds the first available voice matching locale and gender."""
    # Locales: en-US, en-UK, en-AU
    # Gender: Male, Female
    for voice in all_voices:
        if voice.get("locale") == locale and voice.get("gender") == gender:
            # Prefer 'Promo' or 'Narrative' style if available, but take any for now
            return voice["voiceId"]
    return None

@app.get("/voices")
async def get_voices():
    global CACHED_VOICES
    if not CACHED_VOICES:
        all_voices = fetch_murf_voices()
        
        categories = [
            ("American Male", "en-US", "Male"),
            ("American Female", "en-US", "Female"),
            ("British Male", "en-UK", "Male"),
            ("British Female", "en-UK", "Female"),
            ("Australian Male", "en-AU", "Male"),
            ("Australian Female", "en-AU", "Female"),
        ]
        
        start_list = []
        for name, locale, gender in categories:
            vid = get_voice_by_criteria(all_voices, locale, gender)
            if vid:
                start_list.append({"category": name, "id": vid})
            else:
                 start_list.append({"category": name, "id": "placeholder"})
                 
        CACHED_VOICES = start_list

    return CACHED_VOICES

def extract_text_from_pdf(pdf_path: str) -> str:
    text_content = ""
    try:
        with open(pdf_path, "rb") as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content += extracted + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""
    return text_content

def chunk_text(text: str, chunk_size: int = 2000) -> List[str]:
    """Splits text into chunks to respect API limits."""
    # A simple character count split. 
    # Improvement: Split by sentence or paragraph to avoid cutting words.
    chunks = []
    
    # Simple logic: split by double newlines (paragraphs) first
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
            # If a single paragraph is too large, force split it
            while len(current_chunk) > chunk_size:
                chunks.append(current_chunk[:chunk_size])
                current_chunk = current_chunk[chunk_size:]
    
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def call_murf_api(text: str, voice_id: str) -> bytes:
    if not MURF_API_KEY:
        raise Exception("MURF_API_KEY not set")
    
    payload = {
        "voiceId": voice_id,
        "style": "Promo", # Default style.
        "text": text,
        "rate": 0,
        "pitch": 0,
        "sampleRate": 48000,
        "format": "MP3",
        "channel": "Stereo",
        # Murf API (v1/speech/generate) returns JSON with "audioFile" (url) or "encodedImage" (base64)?
        # Actually usually it returns a URL `audioFile`.
        # Let's check the response.
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": MURF_API_KEY
    }
    
    response = requests.post(MURF_API_URL, json=payload, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Murf API Error: {response.status_code} - {response.text}")
        
    data = response.json()
    
    # Check for direct audio URL
    if "audioFile" in data:
        audio_url = data["audioFile"]
        # Download the audio
        audio_res = requests.get(audio_url)
        return audio_res.content
    elif "encodedAudio" in data:
        # If it returns base64
        return base64.b64decode(data["encodedAudio"])
    else:
        raise Exception(f"Unexpected API response: {data}")



@app.get("/download/{filename}")
async def download_audio(filename: str):
    file_path = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path, 
        filename=filename, 
        media_type="audio/mpeg"
    )

@app.post("/convert")
async def convert_pdf(
    file: UploadFile = File(...), 
    voice_id: str = Form(...) 
):
    print(f"Processing conversion for voice: {voice_id}")

    filename = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 1. Extract
        text = extract_text_from_pdf(filepath)
        if not text.strip():
             raise HTTPException(status_code=400, detail="No text extracted from PDF")
             
        # 2. Chunk
        chunks = chunk_text(text)
        print(f"Text split into {len(chunks)} chunks.")
        
        # 3. Generate and Concatenate Audio (MP3) directly
        # We will write chunks directly to the output file as we receive them.
        output_filename = f"audiobook_{uuid.uuid4()}.mp3"
        output_path = os.path.join(AUDIO_DIR, output_filename)
        
        # Create/Clear file
        with open(output_path, "wb") as out_f:
            pass

        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            # Sanitize text to avoid API errors (e.g. "cock" -> "rooster")
            # Use regex to replace whole word only, to avoid changing "peacock"
            if re.search(r'\bcock\b', chunk, re.IGNORECASE):
                print("Sanitizing text: replacing 'cock' with 'rooster'")
                chunk = re.sub(r'\bcock\b', 'rooster', chunk, flags=re.IGNORECASE)

            print(f"Processing chunk {i+1}/{len(chunks)}...")
            try:
                # Get raw MP3 bytes
                raw_audio = call_murf_api(chunk, voice_id)
                
                # Append to file
                with open(output_path, "ab") as out_f:
                    out_f.write(raw_audio)
                    
            except Exception as e:
                print(f"Failed to generate audio for chunk {i}: {e}")
                raise HTTPException(status_code=500, detail=f"Text-to-Speech generation failed: {str(e)}")

        # Clean up input PDF
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # URL for playback (Static serve)
        playback_url = f"{str(requests.Request('GET', 'http://localhost:8000').prepare().url).rstrip('/')}/audio/{output_filename}"
        # We can just return the local relative path or full URL. Frontend constructs it usually? 
        # Actually frontend uses the `download_url` from response.
        # Let's keep `download_url` as the direct download link now? 
        # or separate playback vs download.
        
        # Let's provide both or just the filename so frontend can decide.
        # Original code returned `download_url`.
        
        # In main.py, update the return statement in @app.post("/convert")
        return JSONResponse({
            "status": "success", 
            "download_url": f"/download/{output_filename}",
            "playback_url": f"/audio/{output_filename}", 
            "filename": output_filename
        })

    except HTTPException as he:
        raise he
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e))

