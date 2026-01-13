from fastapi import APIRouter, HTTPException
from app.config import settings
import requests, base64
from typing import List, Dict

router = APIRouter(prefix="/work-items", tags=["Work Items"])


# ---------------- AUTH ----------------
def auth_header():
    token = f":{settings.ADO_PAT}"
    encoded = base64.b64encode(token.encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded}"
    }


# ---------------- ADO CALL ----------------
def ado_post(url: str, payload: dict) -> dict:
    r = requests.post(url, headers=auth_header(), json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()

def chunk_list(items, size=200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ---------------- API ----------------
@router.get("/")
def get_work_items(project: str, iteration_path: str):
    """
    Fetch Stories, Bugs, Tasks, Test Cases for a sprint
    """

    # 1️⃣ WIQL
    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"

    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject] = '{project}'
          AND [System.IterationPath] UNDER '{iteration_path}'
          AND [System.WorkItemType] IN ('User Story','Bug','Task','Test Case')
        """
    }

    wiql_result = ado_post(wiql_url, wiql)
    ids = [item["id"] for item in wiql_result.get("workItems", [])]

    if not ids:
        return []

    # 2️⃣ Batch fetch (SAFE)
    batch_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"

    all_items = []

    for batch in chunk_list(ids, 200):
        payload = {
            "ids": batch,
            "fields": [
                "System.Id",
                "System.WorkItemType",
                "System.Title",
                "System.State",
                "System.CreatedDate",
                "System.ChangedDate",   # ✅ SAFE replacement
                "System.AssignedTo",
                "System.CreatedBy",
                "Microsoft.VSTS.Scheduling.StoryPoints",
                "Microsoft.VSTS.Common.Priority",
                "Microsoft.VSTS.Common.Severity",
                "System.AreaPath",
                "System.IterationPath",
                "System.Parent"
            ]
        }

        response = ado_post(batch_url, payload)
        all_items.extend(response.get("value", []))

    # 3️⃣ Normalize output
    result = []

    for wi in all_items:
        f = wi.get("fields", {})

        result.append({
            "work_item_id": wi["id"],
            "work_item_type": f.get("System.WorkItemType"),
            "title": f.get("System.Title"),
            "state": f.get("System.State"),
            "created_date": f.get("System.CreatedDate"),
            "closed_date": f.get("System.ChangedDate"),  # best available
            "assigned_to": (f.get("System.AssignedTo") or {}).get("displayName"),
            "created_by": (f.get("System.CreatedBy") or {}).get("displayName"),
            "story_points": f.get("Microsoft.VSTS.Scheduling.StoryPoints"),
            "priority": f.get("Microsoft.VSTS.Common.Priority"),
            "severity": f.get("Microsoft.VSTS.Common.Severity"),
            "area_path": f.get("System.AreaPath"),
            "iteration_path": f.get("System.IterationPath"),
            "parent_id": f.get("System.Parent")
        })

    return result