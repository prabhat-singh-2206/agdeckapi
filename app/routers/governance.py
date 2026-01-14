from fastapi import APIRouter
from app.config import settings
from app.ado_client import ado_post, ado_get
from collections import defaultdict
from datetime import datetime, timedelta

router = APIRouter(prefix="/governance", tags=["Governance"])


def derive_role(name: str):
    n = name.upper()
    if "QA" in n:
        return "QA"
    if "LEAD" in n:
        return "Tech Lead"
    return "Developer"


@router.get("/individuals")
def governance_individuals(
    project: str,
    area_path: str,
    iteration_path: str | None = None,
    days: int = 30
):
    """
    Governance View: Individual vs Productivity
    """

    # ---------------- CLEAN INPUT ----------------
    project = project.strip()
    area_path = area_path.strip().replace("\\\\", "\\")  # fix double backslashes
    if iteration_path:
        iteration_path = iteration_path.strip().replace("\\\\", "\\")

    # ---------------- WIQL ----------------
    wiql_conditions = [
        f"[System.TeamProject] = '{project}'",
        f"[System.AreaPath] UNDER '{area_path}'",
        "[System.WorkItemType] IN ('User Story','Bug')"
    ]

    if iteration_path:
        wiql_conditions.append(
            f"[System.IterationPath] = '{iteration_path}'"
        )

    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE {' AND '.join(wiql_conditions)}
        """
    }

    # Debug print to verify exact WIQL sent to ADO
    print("DEBUG WIQL:", wiql)

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
            "iteration_path": iteration_path,
            "individuals": []
        }

    # ---------------- BATCH DETAILS ----------------
    batch_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/workitemsbatch?api-version=7.1"
    )

    payload = {
        "ids": ids,
        "fields": [
            "System.WorkItemType",
            "System.State",
            "System.AssignedTo",
            "System.CreatedBy"
        ]
    }

    items = ado_post(batch_url, payload).get("value", [])

    people = defaultdict(lambda: {
        "stories_completed": 0,
        "bugs_created": 0,
        "bugs_fixed": 0,
        "prs_raised": 0,
        "prs_approved": 0,
        "pr_cycle_times": []
    })

    # ---------------- WORK ITEM METRICS ----------------
    for wi in items:
        f = wi["fields"]
        wi_type = f.get("System.WorkItemType")
        state = f.get("System.State")

        assigned = f.get("System.AssignedTo", {}).get("displayName")
        creator = f.get("System.CreatedBy", {}).get("displayName")

        if wi_type == "User Story" and state == "Closed" and assigned:
            people[assigned]["stories_completed"] += 1

        if wi_type == "Bug":
            if creator:
                people[creator]["bugs_created"] += 1
            if assigned and state == "Closed":
                people[assigned]["bugs_fixed"] += 1

    # ---------------- PR METRICS ----------------
    since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

    repos = ado_get(
        f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/git/repositories?api-version=7.1"
    ).get("value", [])

    for repo in repos:
        repo_id = repo["id"]
        repo_name = repo.get("name", "Unknown")
        try:
            prs = ado_get(
                f"https://dev.azure.com/{settings.ADO_ORG}/{project}/"
                f"_apis/git/repositories/{repo_id}/pullrequests"
                f"?searchCriteria.status=completed"
                f"&searchCriteria.minTime={since}"
                f"&api-version=7.1"
            ).get("value", [])
        except Exception as e:
            print(f"Skipping repo '{repo_name}' due to error: {e}")
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
                    people[r.get("displayName", "Unknown")]["prs_approved"] += 1

    # ---------------- RESPONSE ----------------
    individuals = []

    for name, m in people.items():
        avg_cycle = (
            round(sum(m["pr_cycle_times"]) / len(m["pr_cycle_times"]), 2)
            if m["pr_cycle_times"] else 0
        )

        squad = area_path.split("\\")[-1] if "\\" in area_path else area_path

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
        "iteration_path": iteration_path,
        "individuals": individuals
    }
