from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings

router = APIRouter(prefix="/api/meta", tags=["Metadata"])

def extract_nodes(node, parent=None, level=0, result=[]):
    result.append({
        "area_path": node["path"],
        "parent_path": parent,
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
