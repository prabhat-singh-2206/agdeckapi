from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings

router = APIRouter(prefix="/api/meta", tags=["Metadata"])

@router.get("/projects")
def list_projects():
    url = f"https://dev.azure.com/{settings.ADO_ORG}/_apis/projects?api-version=7.0"
    data = ado_get(url)

    return [
        {
            "project_id": p["id"],
            "project_name": p["name"],
            "state": p["state"],
            "visibility": p["visibility"]
        }
        for p in data.get("value", [])
    ]
