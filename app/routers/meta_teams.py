from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings

router = APIRouter(prefix="/api/meta", tags=["Metadata"])

@router.get("/teams")
def list_teams(project: str):
    url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"_apis/projects/{project}/teams?api-version=7.0"
    )

    data = ado_get(url)

    return [
        {
            "team_id": t["id"],
            "team_name": t["name"],
            "project_name": project
        }
        for t in data.get("value", [])
    ]
