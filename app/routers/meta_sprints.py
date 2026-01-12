from fastapi import APIRouter, HTTPException
from app.config import settings
import requests, base64
from datetime import datetime
from typing import List, Dict
from dateutil import parser

router = APIRouter(prefix="/sprints", tags=["Sprints"])

# ---------------- AUTH ----------------
def auth_header():
    token = f":{settings.ADO_PAT}"
    encoded = base64.b64encode(token.encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded}"
    }

# ---------------- WIQL ----------------
def wiql_user_stories(project: str, iteration_path: str) -> List[int]:
    url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"

    query = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
            [System.TeamProject] = '{project}'
            AND [System.IterationPath] UNDER '{iteration_path}'
            AND [System.WorkItemType] = 'User Story'
        """
    }

    r = requests.post(url, headers=auth_header(), json=query)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return [w["id"] for w in r.json().get("workItems", [])]

# ---------------- BATCH DETAILS ----------------
def get_story_points(project: str, ids: List[int]) -> Dict[str, float]:
    if not ids:
        return {
            "committed_story_points": 0.0,
            "completed_story_points": 0.0,
            "carry_over_story_points": 0.0
        }

    url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"
    payload = {
        "ids": ids,
        "fields": [
            "System.State",
            "Microsoft.VSTS.Scheduling.StoryPoints"
        ]
    }

    r = requests.post(url, headers=auth_header(), json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    committed = completed = 0.0
    DONE = {"Done", "Closed", "Resolved"}

    for wi in r.json()["value"]:
        sp = float(wi["fields"].get("Microsoft.VSTS.Scheduling.StoryPoints") or 0)
        committed += sp
        if wi["fields"]["System.State"] in DONE:
            completed += sp

    return {
        "committed_story_points": committed,
        "completed_story_points": completed,
        "carry_over_story_points": committed - completed
    }

# ---------------- API ----------------
@router.get("/")
def get_sprints(project: str, team: str):

    result = []

    it_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/{team}/_apis/work/teamsettings/iterations"
        f"?api-version=7.1-preview.1"
    )

    iterations = requests.get(it_url, headers=auth_header()).json().get("value", [])

    for it in iterations:
        attr = it["attributes"]

        if not attr.get("startDate") or not attr.get("finishDate"):
            continue

        start = parser.isoparse(attr["startDate"])
        end = parser.isoparse(attr["finishDate"])

        iteration_path = it["path"]  # 🔥 THIS IS THE KEY FIX

        ids = wiql_user_stories(project, iteration_path)
        points = get_story_points(project, ids)

        result.append({
            "project_name": project,
            "team_name": team,
            "sprint_id": it["id"],
            "sprint_name": it["name"],
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "duration_days": (end - start).days + 1,
            **points,
            "sprint_goal": attr.get("goal", "")
        })

    return result
