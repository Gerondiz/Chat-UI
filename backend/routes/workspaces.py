import logging

from fastapi import APIRouter, HTTPException

import workspace_db


logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces"])


@router.get("/api/workspaces")
async def list_workspaces():
    return {"workspaces": workspace_db.list_workspaces()}


@router.post("/api/workspaces")
async def create_workspace(data: dict):
    ws = workspace_db.create_workspace(data)
    return ws


@router.get("/api/workspaces/{ws_id}")
async def get_workspace(ws_id: int):
    ws = workspace_db.get_workspace(ws_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.put("/api/workspaces/{ws_id}")
async def update_workspace(ws_id: int, data: dict):
    ws = workspace_db.update_workspace(ws_id, data)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.delete("/api/workspaces/{ws_id}")
async def delete_workspace(ws_id: int):
    ok = workspace_db.delete_workspace(ws_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "ok"}
