from fastapi import APIRouter
from app.config import settings
from app.ado_client import ado_post
from collections import defaultdict

router = APIRouter(prefix="/bugs-quality", tags=["Bug Quality"])


def chunk(ids, size=200):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def normalize_iteration_path(path: str):
    return path.replace("\\Iteration\\", "\\") if path else path


@router.get("/")
def bug_quality(project: str, iteration_path: str):

    iteration_path = normalize_iteration_path(iteration_path)

    # 1️⃣ WIQL – Bug IDs only
    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"

    wiql = {
        "query": f"""
        SELECT [System.Id]
        FROM WorkItems
        WHERE
          [System.TeamProject] = '{project}'
          AND [System.WorkItemType] = 'Bug'
          AND [System.IterationPath] UNDER '{iteration_path}'
        """
    }

    wiql_res = ado_post(wiql_url, wiql)
    ids = [x["id"] for x in wiql_res.get("workItems", [])]

    if not ids:
        return {"bugs": [], "derived_metrics": {}}

    # 2️⃣ Batch fetch (system fields ONLY)
    batch_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/wit/workitemsbatch?api-version=7.1"
    )

    bugs = []

    for batch in chunk(ids):
        payload = {
            "ids": batch,
            "fields": [
                "System.Id",
                "System.Title",
                "System.State",
                "System.CreatedDate",
                "Microsoft.VSTS.Common.ClosedDate",
                "Microsoft.VSTS.Common.Severity",
                "System.AssignedTo",
                "System.IterationPath",
                "System.Parent"
            ]
        }

        data = ado_post(batch_url, payload).get("value", [])
        bugs.extend(data)

    # 3️⃣ Normalize + Metrics
    output = []
    stats = defaultdict(int)

    sprint_name = iteration_path.split("\\")[-1]

    for b in bugs:
        f = b.get("fields", {})

        assigned_dev = (f.get("System.AssignedTo") or {}).get("displayName")

        stats["total"] += 1
        stats[f"sprint_{sprint_name}"] += 1

        if assigned_dev:
            stats[f"dev_{assigned_dev}"] += 1

        # ❗ FoundIn not available → mark Unknown
        stats["unknown_stage"] += 1

        output.append({
            "bug_id": b.get("id"),
            "bug_title": f.get("System.Title"),
            "bug_created_date": f.get("System.CreatedDate"),
            "bug_closed_date": f.get("Microsoft.VSTS.Common.ClosedDate"),
            "severity": f.get("Microsoft.VSTS.Common.Severity"),
            "found_in": "Unknown",  # populate later if field exists
            "introduced_sprint": None,
            "found_sprint": normalize_iteration_path(f.get("System.IterationPath")),
            "linked_story_id": f.get("System.Parent"),
            "assigned_dev": assigned_dev
        })

    # 4️⃣ Derived KPIs
    derived = {
        "total_bugs": stats["total"],
        "bugs_per_sprint": stats[f"sprint_{sprint_name}"],
        "bugs_by_individual": {
            k.replace("dev_", ""): v
            for k, v in stats.items()
            if k.startswith("dev_")
        }
    }

    return {
        "bugs": output,
        "derived_metrics": derived
    }
