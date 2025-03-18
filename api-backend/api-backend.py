from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import spacy
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import re
import os

app = FastAPI()

# Chargement du modèle NLP de spaCy
nlp = spacy.load("en_core_web_sm")

# Configuration de la base de données
DB_CONFIG = {
    "dbname": "synthese_db",
    "user": "user",
    "password": "password",
    "host": "db",
    "port": 5432
}

# Connexion à la base de données
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

# Modèle de requête
class URLRequest(BaseModel):
    url: str

# Fonction pour extraire le transcript d'une vidéo YouTube
def get_youtube_transcript(video_id: str):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la récupération du transcript : {str(e)}")

# Fonction pour récupérer le contenu texte d'une page web
def fetch_webpage_text(url: str):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text[:500]  # Récupère les 500 premiers caractères pour test
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de la récupération du texte : {str(e)}")

# Fonction pour générer un résumé avec Sumy (TextRank)
def generate_summary(text: str, num_sentences: int = 5):
    parser = PlaintextParser.from_string(text, Tokenizer("french"))
    summarizer = LexRankSummarizer()
    summary = summarizer(parser.document, num_sentences)
    return " ".join([str(sentence) for sentence in summary])

# Endpoint pour traiter une URL
@app.post("/process")
def process_url(request: URLRequest):
    if "youtube.com" in request.url or "youtu.be" in request.url:
        video_id = request.url.split("v=")[-1].split("&")[0]
        transcript = get_youtube_transcript(video_id)
    else:
        transcript = fetch_webpage_text(request.url)
    
    # Génération d'un résumé structuré
    summary = generate_summary(transcript, num_sentences=5)
    
    # Sauvegarde en base
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO documents (url, transcript, summary)
            VALUES (%s, %s, %s) RETURNING id
        """, (request.url, transcript, summary))
        doc_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'insertion en base : {str(e)}")
    
    return {"document_id": doc_id, "summary": summary}
