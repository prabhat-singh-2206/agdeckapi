import base64
import requests
from app.config import settings

def get_headers():
    token = f":{settings.ADO_PAT}"
    encoded = base64.b64encode(token.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json"
    }

def ado_get(url: str):
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()
