from fastapi import APIRouter
from app.config import settings
from app.ado_client import ado_post

router = APIRouter(prefix="/on-time", tags=["On-Time"])


@router.get("/")
def on_time(project: str, iteration_path: str):

    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject]='{project}'
          AND [System.WorkItemType]='User Story'
          AND [System.IterationPath]='{iteration_path}'
        """
    }

    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"
    ids = [x["id"] for x in ado_post(wiql_url, wiql).get("workItems", [])]

    payload = {
        "ids": ids,
        "fields": [
            "System.CreatedDate",
            "Microsoft.VSTS.Common.ClosedDate"
        ]
    }

    batch_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"
    return ado_post(batch_url, payload).get("value", [])
