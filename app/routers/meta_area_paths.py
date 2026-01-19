from fastapi import APIRouter
from app.ado_client import ado_get
from app.config import settings

router = APIRouter(prefix="/api/meta", tags=["Metadata"])


def clean_area_path(path: str) -> str:
    """
    Remove '<Project>\\Area' from area paths
    """
    if "\\Area\\" in path:
        return path.replace("\\Area\\", "\\")
    if path.endswith("\\Area"):
        return path.replace("\\Area", "")
    return path


def extract_nodes(node, level=0, result=None):
    if result is None:
        result = []

    raw_path = node.get("path")
    if not raw_path:
        return result

    cleaned_path = clean_area_path(raw_path.lstrip("\\"))

    parent_path = (
        cleaned_path.rsplit("\\", 1)[0]
        if "\\" in cleaned_path
        else None
    )

    result.append({
        "area_path": cleaned_path,
        "parent_path": parent_path,
        "level": level
    })

    for child in node.get("children", []):
        extract_nodes(child, level + 1, result)

    return result


@router.get("/area-paths")
def area_paths(project: str):
    url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/classificationnodes/areas"
        "?$depth=10&api-version=7.0"
    )

    data = ado_get(url)

    result = []

    # ✅ ALWAYS add project root
    result.append({
        "area_path": project,
        "parent_path": None,
        "level": 0
    })

    # ✅ Add children (if present)
    for child in data.get("children", []):
        extract_nodes(child, 1, result)

    return result
