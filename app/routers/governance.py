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
def fetch_wi_revisions(project, wid):
    """
    Isolated function for parallel execution to fetch history.
    Using lru_cache ensures we don't fetch the same ID twice across requests.
    """
    url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workItems/{wid}/revisions?api-version=7.1"
    try:
        res = ado_get(url)
        # Extract unique display names from revisions
        return {
            rev.get("fields", {}).get("System.ChangedBy", {}).get("displayName")
            for rev in res.get("value", [])
            if rev.get("fields", {}).get("System.ChangedBy")
        }
    except:
        return set()

@router.get("/individuals")
def governance_individuals(
    project: str,
    area_path: str,
    days: int = Query(30, gt=0, le=365)
):
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 1. Fetch Work Item IDs (WIQL is fast)
    wiql_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/wiql?api-version=7.1"
    wiql = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}' AND [System.AreaPath] UNDER '{area_path}' AND [System.ChangedDate] >= '{since}'"
    }
    ids = [w["id"] for w in ado_post(wiql_url, wiql).get("workItems", [])]

    if not ids:
        return {"individuals": []}

    # 2. BATCH Fetch Work Item Types (Massive Speedup vs individual calls)
    # This replaces individual 'get' calls for work item details.
    batch_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/wit/workitemsbatch?api-version=7.1"
    type_map = {}
    for i in range(0, len(ids), 200):
        batch = ids[i:i+200]
        items = ado_post(batch_url, {"ids": batch, "fields": ["System.WorkItemType"]}).get("value", [])
        for item in items:
            type_map[item["id"]] = item.get("fields", {}).get("System.WorkItemType")

    # 3. HIGH-SPEED Parallel Revision Fetching
    # Increased max_workers to 50 for I/O bound tasks to maximize bandwidth
    contribution = defaultdict(lambda: {"User Stories": 0, "Bugs": 0, "PRs": 0})
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_wid = {executor.submit(fetch_wi_revisions, project, wid): wid for wid in ids}
        
        for future in as_completed(future_to_wid):
            wid = future_to_wid[future]
            wtype = type_map.get(wid)
            contributors = future.result()
            
            for user in contributors:
                if wtype in STORY_TYPES:
                    contribution[user]["User Stories"] += 1
                elif wtype == "Bug":
                    contribution[user]["Bugs"] += 1

    # 4. Optimized PR Fetching
    pr_since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    repos = ado_get(f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/git/repositories?api-version=7.1").get("value", [])
    
    # Only fetch PRs for repos that had activity (optional: can be further optimized)
    for repo in repos:
        pr_url = f"https://dev.azure.com/{settings.ADO_ORG}/{project}/_apis/git/repositories/{repo['id']}/pullrequests?searchCriteria.minTime={pr_since}&searchCriteria.status=completed&api-version=7.1"
        prs = ado_get(pr_url).get("value", [])
        for pr in prs:
            owner = pr.get("createdBy", {}).get("displayName")
            if owner:
                contribution[owner]["PRs"] += 1

    # 5. Build Final Response
    individuals = [
        {
            "name": name,
            "metrics": {**stats, "total": sum(stats.values())}
        } for name, stats in contribution.items()
    ]

    return {
        "project": project,
        "area_path": area_path,
        "individuals": sorted(individuals, key=lambda x: x["metrics"]["total"], reverse=True)
    }