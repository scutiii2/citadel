# apps/Ember/ember_api/src/routes/admin_tuning.py
"""/api/admin/tuning: legion's runtime tuning (token limits, failover, classifier).

Needs tuning.manage. legion validates and stores the edit in its overlay file; each
agent applies it at the start of its next turn. Every change is written to the activity log."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.routes.agent_admin import _call, get_agent_admin
from src.services.agent_admin import AgentAdmin
from src.services.log_service import LogWriter
from src.services.permissions import TUNING_MANAGE

router = APIRouter(prefix="/api/admin/tuning", tags=["tuning"])

require_tuning_manage = require_permission(TUNING_MANAGE)


class TuningChangesIn(BaseModel):
    changes: dict[str, Any]


@router.get("")
async def read_tuning(account: Account = Depends(require_tuning_manage), admin: AgentAdmin = Depends(get_agent_admin)) -> Any:
    return await _call(admin.tuning(account))


@router.put("")
async def update_tuning(
    body: TuningChangesIn,
    account: Account = Depends(require_tuning_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    before = await _call(admin.tuning(account))
    view = await _call(admin.set_tuning(account, body.changes))
    await logs.write("action", account.id, "tuning.update", "Changed tuning: " + ", ".join(body.changes)[:400],
                     details=json.dumps({"before": before, "after": view}))
    return view
