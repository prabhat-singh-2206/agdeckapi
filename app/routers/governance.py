from fastapi import APIRouter, HTTPException
from app.config import settings
from app.ado_client import ado_get, ado_post
from collections import defaultdict
from datetime import datetime, timedelta

router = APIRouter(prefix="/governance", tags=["Governance"])


# ---------------- HELPERS ----------------
def chunk_list(items, size=200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def derive_role(name: str):
    n = name.upper()
    if "QA" in n:
        return "QA"
    if "LEAD" in n:
        return "Tech Lead"
    return "Developer"


# ---------------- API ----------------
@router.get("/individuals")
def governance_individuals(
    project: str,
    area_path: str,
    days: int = 30
):
    """
    Governance – Individual & Role Mapping

    Filters:
    - Project
    - Area Path
    - Last N days (ChangedDate)
    """

    # ---------------- CLEAN INPUT ----------------
    project = project.strip()
    area_path = area_path.strip().replace("\\\\", "\\")
    since_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    # ---------------- WIQL (SAFE + BOUNDED) ----------------
    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject] = '{project}'
          AND [System.AreaPath] UNDER '{area_path}'
          AND [System.WorkItemType] IN ('User Story','Bug')
          AND [System.ChangedDate] >= '{since_date}'
        """
    }

    wiql_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/wiql?api-version=7.1"
    )

    wiql_res = ado_post(wiql_url, wiql)
    ids = [i["id"] for i in wiql_res.get("workItems", [])]

    if not ids:
        return {
            "project": project,
            "area_path": area_path,
            "days": days,
            "individuals": []
        }

    # ---------------- WORK ITEM DETAILS ----------------
    batch_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/workitemsbatch?api-version=7.1"
    )

    people = defaultdict(lambda: {
        "stories_completed": 0,
        "bugs_created": 0,
        "bugs_fixed": 0,
        "prs_raised": 0,
        "prs_approved": 0,
        "pr_cycle_times": []
    })

    for batch in chunk_list(ids):
        payload = {
            "ids": batch,
            "fields": [
                "System.WorkItemType",
                "System.State",
                "System.AssignedTo",
                "System.CreatedBy"
            ]
        }

        items = ado_post(batch_url, payload).get("value", [])

        for wi in items:
            f = wi["fields"]
            wi_type = f.get("System.WorkItemType")
            state = f.get("System.State")

            assigned = (f.get("System.AssignedTo") or {}).get("displayName")
            creator = (f.get("System.CreatedBy") or {}).get("displayName")

            if wi_type == "User Story" and state == "Closed" and assigned:
                people[assigned]["stories_completed"] += 1

            if wi_type == "Bug":
                if creator:
                    people[creator]["bugs_created"] += 1
                if assigned and state == "Closed":
                    people[assigned]["bugs_fixed"] += 1

    # ---------------- PR METRICS ----------------
    since_iso = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    repos = ado_get(
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/git/repositories?api-version=7.1"
    ).get("value", [])

    for repo in repos:
        repo_id = repo["id"]

        try:
            prs = ado_get(
                f"https://dev.azure.com/{settings.ADO_ORG}/{project}"
                f"/_apis/git/repositories/{repo_id}/pullrequests"
                f"?searchCriteria.status=completed"
                f"&searchCriteria.minTime={since_iso}"
                f"&api-version=7.1"
            ).get("value", [])
        except Exception:
            continue

        for pr in prs:
            creator = pr["createdBy"].get("displayName")
            if not creator:
                continue

            created = datetime.fromisoformat(pr["creationDate"][:-1])
            merged = datetime.fromisoformat(pr["closedDate"][:-1])

            people[creator]["prs_raised"] += 1
            people[creator]["pr_cycle_times"].append(
                (merged - created).days
            )

            for r in pr.get("reviewers", []):
                if r.get("vote", 0) > 0:
                    reviewer = r.get("displayName")
                    if reviewer:
                        people[reviewer]["prs_approved"] += 1

    # ---------------- RESPONSE ----------------
    squad = area_path.split("\\")[-1]

    individuals = []
    for name, m in people.items():
        avg_cycle = (
            round(sum(m["pr_cycle_times"]) / len(m["pr_cycle_times"]), 2)
            if m["pr_cycle_times"] else 0
        )

        individuals.append({
            "user_id": name,
            "name": name,
            "role": derive_role(name),
            "squad": squad,
            "project": project,
            "activity_metrics": {
                "stories_completed": m["stories_completed"],
                "bugs_created": m["bugs_created"],
                "bugs_fixed": m["bugs_fixed"],
                "prs_raised": m["prs_raised"],
                "prs_approved": m["prs_approved"],
                "avg_pr_cycle_time_days": avg_cycle
            }
        })

    return {
        "project": project,
        "area_path": area_path,
        "days": days,
        "individuals": individuals
    }
