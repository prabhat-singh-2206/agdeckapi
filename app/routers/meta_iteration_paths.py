from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings
from datetime import datetime

router = APIRouter(prefix="/api/meta", tags=["Metadata"])

def extract_iterations(node, parent=None, level=0, result=[]):
    attrs = node.get("attributes", {})
    start = attrs.get("startDate")
    end = attrs.get("finishDate")

    duration = None
    if start and end:
        s = datetime.fromisoformat(start[:10])
        e = datetime.fromisoformat(end[:10])
        duration = (e - s).days + 1

    result.append({
        "iteration_path": node["path"],
        "sprint_name": node["name"],
        "start_date": start,
        "end_date": end,
        "duration_days": duration,
        "level": level
    })

    for child in node.get("children", []):
        extract_iterations(child, node["path"], level + 1, result)

    return result

@router.get("/iterations")
def iteration_paths(project: str):
    url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/classificationnodes/iterations"
        "?$depth=10&api-version=7.0"
    )

    data = ado_get(url)
    return extract_iterations(data)
