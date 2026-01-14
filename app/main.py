from fastapi import FastAPI
from .routers import (
    meta_projects,
    meta_teams,
    meta_area_paths,
    meta_iteration_paths,
    meta_sprints,
    work_items,
    bug_quality,
    efficiency,
    ontime,
    quality,
    governance,
    prs      
)

app = FastAPI(title="ADO Metadata APIs")

app.include_router(meta_projects.router)
app.include_router(meta_teams.router)
app.include_router(meta_area_paths.router)
app.include_router(meta_iteration_paths.router)
app.include_router(meta_sprints.router)
app.include_router(work_items.router)
app.include_router(bug_quality.router)
app.include_router(efficiency.router)
app.include_router(ontime.router)
app.include_router(quality.router)
app.include_router(governance.router) 
app.include_router(prs.router)
