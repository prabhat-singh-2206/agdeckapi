from fastapi import APIRouter, HTTPException
from app.config import settings
from app.ado_client import ado_post
from collections import defaultdict

router = APIRouter(prefix="/governance", tags=["Governance"])


def chunk(ids, size=200):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


@router.get("/")
def governance(
    project: str,
    iteration_path: str
):
    """
    Governance metrics scoped to a sprint / iteration
    """

    # 1️⃣ WIQL (Scoped – prevents 20k limit)
    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject] = '{project}'
          AND [System.IterationPath] UNDER '{iteration_path}'
          AND [System.WorkItemType] IN ('User Story','Bug')
        """
    }

    wiql_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/wiql?api-version=7.1"
    )

    wiql_res = ado_post(wiql_url, wiql)
    ids = [x["id"] for x in wiql_res.get("workItems", [])]

    if not ids:
        return {}

    # 2️⃣ Batch fetch
    batch_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/workitemsbatch?api-version=7.1"
    )

    stats = defaultdict(lambda: {
        "stories_completed": 0,
        "bugs_created": 0,
        "bugs_fixed": 0
    })

    for batch in chunk(ids):
        payload = {
            "ids": batch,
            "fields": [
                "System.WorkItemType",
                "System.State",
                "System.AssignedTo"
            ]
        }

        items = ado_post(batch_url, payload).get("value", [])

        for wi in items:
            f = wi["fields"]
            user = (f.get("System.AssignedTo") or {}).get(
                "displayName", "Unassigned"
            )

            if f["System.WorkItemType"] == "User Story":
                if f["System.State"] in ["Done", "Closed", "Resolved"]:
                    stats[user]["stories_completed"] += 1

            if f["System.WorkItemType"] == "Bug":
                stats[user]["bugs_created"] += 1
                if f["System.State"] in ["Done", "Closed", "Resolved"]:
                    stats[user]["bugs_fixed"] += 1

    return {
        "project": project,
        "iteration_path": iteration_path,
        "individual_metrics": stats
    }
