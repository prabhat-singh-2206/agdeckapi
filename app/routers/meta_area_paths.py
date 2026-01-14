from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings

router = APIRouter(prefix="/api/meta", tags=["Metadata"])


def extract_nodes(node, parent=None, level=0, result=None):
    if result is None:
        result = []

    # Remove leading backslash from node path
    area_path = node["path"].lstrip("\\") if node.get("path") else None
    parent_path = parent.lstrip("\\") if parent else None

    result.append({
        "area_path": area_path,
        "parent_path": parent_path,
        "level": level
    })

    for child in node.get("children", []):
        extract_nodes(child, node["path"], level + 1, result)

    return result


@router.get("/area-paths")
def area_paths(project: str):
    url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/classificationnodes/areas"
        "?$depth=10&api-version=7.0"
    )

    data = ado_get(url)
    return extract_nodes(data)
