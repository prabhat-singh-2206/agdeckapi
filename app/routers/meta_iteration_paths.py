from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings
from datetime import datetime
from typing import Dict, List

router = APIRouter(prefix="/api/meta", tags=["Metadata"])


def clean_iteration_path(path: str) -> str:
    """
    Ensures no leading backslashes.
    DOES NOT modify valid hierarchy.
    """
    """
    Removes the 'Iteration' node from Azure DevOps iteration paths
    """
    if not path:
        return ""

    parts = path.strip("\\").split("\\")
    cleaned = [p for p in parts if p.lower() != "iteration"]
    return "\\".join(cleaned)


def extract_iterations(
    node: Dict,
    level: int = 0,
    result: List[Dict] | None = None
):
    if result is None:
        result = []

    attrs = node.get("attributes", {})
    start = attrs.get("startDate")
    end = attrs.get("finishDate")

    duration = None
    if start and end:
        s = datetime.fromisoformat(start[:10])
        e = datetime.fromisoformat(end[:10])
        duration = (e - s).days + 1

    raw_path = clean_iteration_path(node.get("path", ""))

    result.append({
        "iteration_path": raw_path,
        "sprint_name": node.get("name"),
        "start_date": start,
        "end_date": end,
        "duration_days": duration,
        "level": level
    })

    for child in node.get("children", []):
        extract_iterations(child, level + 1, result)

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
