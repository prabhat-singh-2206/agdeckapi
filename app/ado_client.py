import requests
import base64
from app.config import settings
from fastapi import HTTPException

def _auth_header():
    token = f":{settings.ADO_PAT}"
    encoded = base64.b64encode(token.encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded}"
    }

def ado_get(url: str):
    r = requests.get(url, headers=_auth_header())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

def ado_post(url: str, payload: dict):
    r = requests.post(url, headers=_auth_header(), json=payload)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
