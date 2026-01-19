from fastapi import APIRouter, Query
from collections import defaultdict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.ado_client import ado_post, ado_get
from app.config import settings
import functools

router = APIRouter(prefix="/governance", tags=["Governance"])

STORY_TYPES = ["User Story", "Requirement", "Product Backlog Item"]

@functools.lru_cache(maxsize=2048)
def fetch_wi_revisions(project: str, wid: int):
    """
    Fetches unique contributors from a work item's history.
    Cached to prevent redundant calls across different API requests.
    """
    url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workItems/{wid}/revisions?api-version=7.1"
    try:
        res = ado_get(url)
        return {
            rev.get("fields", {}).get("System.ChangedBy", {}).get("displayName")
            for rev in res.get("value", [])
            if rev.get("fields", {}).get("System.ChangedBy")
        }
    except Exception:
        return set()

@router.get("/individuals")
def governance_individuals(
    project: str,
    area_path: str,
    days: int = Query(30, gt=0, le=365)
):
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 1. Fetch Work Item IDs via WIQL (Fast)
    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"
    wiql = {
        "query": f"""
            SELECT [System.Id] FROM WorkItems 
            WHERE [System.TeamProject] = '{project}' 
            AND [System.AreaPath] UNDER '{area_path}' 
            AND [System.ChangedDate] >= '{since}'
        """
    }
    
    wi_data = ado_post(wiql_url, wiql).get("workItems", [])
    ids = [w["id"] for w in wi_data]

    contribution = defaultdict(lambda: {"User Stories": 0, "Bugs": 0, "PRs": 0})

    if not ids:
        return {"project": project, "area_path": area_path, "individuals": []}

    # 2. Batch Fetch Work Item Types (200 at a time)
    batch_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"
    type_map = {}
    for i in range(0, len(ids), 200):
        batch = ids[i : i + 200]
        items = ado_post(batch_url, {"ids": batch, "fields": ["System.WorkItemType"]}).get("value", [])
        for item in items:
            type_map[item["id"]] = item.get("fields", {}).get("System.WorkItemType")

    # 3. Parallel Execution for Work Item History (Massive Speedup)
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_wid = {executor.submit(fetch_wi_revisions, project, wid): wid for wid in ids}
        
        for future in as_completed(future_to_wid):
            wid = future_to_wid[future]
            wtype = type_map.get(wid)
            contributors = future.result()
            
            for user in contributors:
                if not user: continue
                if wtype in STORY_TYPES:
                    contribution[user]["User Stories"] += 1
                elif wtype == "Bug":
                    contribution[user]["Bugs"] += 1

    # 4. PR Fetching with Robust Error Handling (Fixes 404/Permission issues)
    pr_since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    try:
        repos_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/git/repositories?api-version=7.1"
        repos = ado_get(repos_url).get("value", [])
        
        # We process PRs repo by repo, but wrap in try-except to avoid crashing on restricted repos
        for repo in repos:
            repo_id = repo.get("id")
            try:
                pr_url = (f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/git/repositories/{repo_id}/pullrequests"
                          f"?searchCriteria.minTime={pr_since}&searchCriteria.status=completed&api-version=7.1")
                prs_res = ado_get(pr_url)
                prs = prs_res.get("value", [])
                
                for pr in prs:
                    owner = pr.get("createdBy", {}).get("displayName")
                    if owner:
                        contribution[owner]["PRs"] += 1
            except Exception:
                # Silently skip repositories that return 404 or No Permissions
                continue
    except Exception:
        # If the main repo list fails, we simply return the Work Item contributions
        pass

    # 5. Format and Sort Final Result
    individuals = [
        {
            "name": name,
            "metrics": {
                "user_stories": stats["User Stories"],
                "bugs": stats["Bugs"],
                "prs": stats["PRs"],
                "total": sum(stats.values())
            }
        } for name, stats in contribution.items()
    ]
    
    # Sort by total activity descending
    individuals.sort(key=lambda x: x["metrics"]["total"], reverse=True)

    return {
        "project": project,
        "area_path": area_path,
        "individuals": individuals
    }