from fastapi import APIRouter
from app.config import settings
from app.ado_client import ado_post

router = APIRouter(prefix="/quality", tags=["Quality"])


def chunk(ids, size=200):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


@router.get("/")
def quality_data(project: str, iteration_path: str):
    """
    Bug + Story entity for Quality %
    """

    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject] = '{project}'
          AND [System.IterationPath] UNDER '{iteration_path}'
          AND [System.WorkItemType] IN ('Bug','User Story')
        """
    }

    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"
    ids = [x["id"] for x in ado_post(wiql_url, wiql).get("workItems", [])]

    if not ids:
        return []

    result = []

    batch_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"

    for batch in chunk(ids):
        payload = {
            "ids": batch,
            "fields": [
                "System.Id",
                "System.WorkItemType",
                "System.Title",
                "System.State",
                "System.CreatedDate",
                "Microsoft.VSTS.Common.ClosedDate",
                "Microsoft.VSTS.Common.Severity",
                "Microsoft.VSTS.Common.Priority",
                "System.AssignedTo",
                "Microsoft.VSTS.Scheduling.StoryPoints",
                "System.IterationPath",
                "System.Parent"
            ]
        }

        items = ado_post(batch_url, payload).get("value", [])

        for wi in items:
            f = wi["fields"]
            result.append({
                "work_item_id": wi["id"],
                "type": f.get("System.WorkItemType"),
                "title": f.get("System.Title"),
                "state": f.get("System.State"),
                "created_date": f.get("System.CreatedDate"),
                "closed_date": f.get("Microsoft.VSTS.Common.ClosedDate"),
                "severity": f.get("Microsoft.VSTS.Common.Severity"),
                "priority": f.get("Microsoft.VSTS.Common.Priority"),
                "assigned_to": (f.get("System.AssignedTo") or {}).get("displayName"),
                "story_points": f.get("Microsoft.VSTS.Scheduling.StoryPoints"),
                "iteration_path": f.get("System.IterationPath"),
                "linked_story_id": f.get("System.Parent")
            })

    return result
