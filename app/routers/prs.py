from fastapi import APIRouter, Query
from app.config import settings
from app.ado_client import ado_get
from datetime import datetime, timedelta

router = APIRouter(prefix="/prs", tags=["PR Activity"])


@router.get("/")
def pr_activity(
    project: str,
    days: int = Query(
        90,
        description="Number of days to fetch PRs for",
        ge=1
    )
):
    """
    Fetch PR activity for the last N days (user-defined)
    """

    cutoff = datetime.utcnow() - timedelta(days=days)

    repo_url = (
        f"https://dev.azure.com/{settings.ADO_ORG}/"
        f"{project}/_apis/git/repositories?api-version=7.1"
    )

    repos = ado_get(repo_url).get("value", [])

    all_prs = []
    skipped_repos = []

    for repo in repos:
        repo_id = repo.get("id")
        repo_name = repo.get("name")

        pr_url = (
            f"https://dev.azure.com/{settings.ADO_ORG}/"
            f"{project}/_apis/git/repositories/{repo_id}/pullrequests"
            f"?searchCriteria.status=all&api-version=7.1"
        )

        try:
            prs = ado_get(pr_url).get("value", [])
        except Exception:
            skipped_repos.append(repo_name)
            continue

        for pr in prs:
            created = datetime.fromisoformat(
                pr["creationDate"].replace("Z", "")
            )

            if created < cutoff:
                continue  # ⛔ skip old PRs

            merged = pr.get("closedDate")
            merged_dt = (
                datetime.fromisoformat(merged.replace("Z", ""))
                if merged else None
            )

            all_prs.append({
                "repository": repo_name,
                "pr_id": pr["pullRequestId"],
                "created_by": pr["createdBy"]["displayName"],
                "reviewed_by": [
                    r["displayName"] for r in pr.get("reviewers", [])
                ],
                "created_date": pr["creationDate"],
                "merged_date": merged,
                "cycle_time_days": (
                    (merged_dt - created).days
                    if merged_dt else None
                ),
                "status": pr["status"]
            })

    return {
        "project": project,
        "days": days,
        "total_prs": len(all_prs),
        "skipped_repositories": skipped_repos,
        "prs": all_prs
    }
