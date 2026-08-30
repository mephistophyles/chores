"""HTTP surface: the board, the completion log, and the config editor."""

import logging
import json
import sys
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config, cycles, db, repo
from .auth import Identity, identity, require_write

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
log = logging.getLogger("chores")


def jlog(event: str, **fields) -> None:
    log.info(json.dumps({"event": event, **fields}))


# Fail at startup rather than serving a bare API with mystery 404s.
if not config.WEB_DIST.is_dir():
    raise RuntimeError(f"WEB_DIST not found at {config.WEB_DIST}")
INDEX_HTML = config.WEB_DIST / "index.html"
if not INDEX_HTML.is_file():
    raise RuntimeError(f"index.html not found in {config.WEB_DIST}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open(wait=True, timeout=15)
    jlog("startup", auth_mode=config.AUTH_MODE, timezone=config.TIMEZONE)
    try:
        yield
    finally:
        # SIGTERM lands here: uvicorn drains in-flight requests, then we close.
        db.pool.close()
        jlog("shutdown")


app = FastAPI(title="Chores", lifespan=lifespan, docs_url=None, redoc_url=None)


def resolve_day(on: str | None) -> date:
    if not on:
        return cycles.today()
    try:
        return date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=400, detail="`on` must be YYYY-MM-DD")


# ---------------------------------------------------------------- health

@app.get("/healthz")
def healthz():
    try:
        db.check()
    except Exception as exc:  # noqa: BLE001 - the gate wants any failure
        jlog("healthz.fail", error=type(exc).__name__)
        return JSONResponse({"ok": False, "error": "database"}, status_code=503)
    if not INDEX_HTML.is_file():
        return JSONResponse({"ok": False, "error": "assets"}, status_code=503)
    return {"ok": True}


# ---------------------------------------------------------------- board

@app.get("/api/board")
def get_board(on: str | None = None, who: Identity = Depends(identity)):
    day = resolve_day(on)
    with db.session(who.user_id) as conn:
        data = repo.board(conn, day)
        data["assignees"] = repo.assignees(conn)
    data["me"] = who.user_id
    data["may_write"] = who.may_write
    return data


class CheckIn(BaseModel):
    checked: bool
    on: str | None = None


@app.post("/api/chores/{chore_id}/check")
def set_check(chore_id: int, body: CheckIn, who: Identity = Depends(identity)):
    require_write(who)
    day = resolve_day(body.on)
    action = "check" if body.checked else "uncheck"
    with db.session(who.user_id) as conn:
        event = repo.record_event(conn, chore_id, action, who.user_id, day)
        if not event:
            raise HTTPException(status_code=404, detail="chore not found")
        data = repo.board(conn, day)
    jlog("chore.event", chore_id=chore_id, action=action, period=event["period_key"])
    return data


# ---------------------------------------------------------------- history

@app.get("/api/history")
def get_history(
    limit: int = Query(default=50, ge=1, le=config.MAX_PAGE_SIZE),
    before_id: int | None = Query(default=None, ge=1),
    who: Identity = Depends(identity),
):
    with db.session(who.user_id) as conn:
        rows = repo.history(conn, limit, before_id)
    return {
        "events": [
            {
                "id": r["id"],
                "chore_id": r["chore_id"],
                "chore_text": r["chore_text"],
                "category_name": r["category_name"],
                "cycle": r["cycle"],
                "period_key": r["period_key"],
                "action": r["action"],
                "user_id": r["user_id"],
                "occurred_at": r["occurred_at"].isoformat(),
            }
            for r in rows
        ],
        "next_before_id": rows[-1]["id"] if len(rows) == limit else None,
    }


# ---------------------------------------------------------------- config

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cycle: str = "weekly"
    descriptor: str = Field(default="", max_length=120)

    @field_validator("cycle")
    @classmethod
    def known_cycle(cls, v: str) -> str:
        if v not in cycles.CYCLES:
            raise ValueError(f"cycle must be one of {', '.join(cycles.CYCLES)}")
        return v


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    cycle: str | None = None
    descriptor: str | None = Field(default=None, max_length=120)
    position: int | None = Field(default=None, ge=0, le=999)

    @field_validator("cycle")
    @classmethod
    def known_cycle(cls, v: str | None) -> str | None:
        if v is not None and v not in cycles.CYCLES:
            raise ValueError(f"cycle must be one of {', '.join(cycles.CYCLES)}")
        return v


class ChoreIn(BaseModel):
    category_id: int
    text: str = Field(min_length=1, max_length=200)
    assignee: str | None = Field(default=None, max_length=60)


class ChorePatch(BaseModel):
    category_id: int | None = None
    text: str | None = Field(default=None, min_length=1, max_length=200)
    assignee: str | None = Field(default=None, max_length=60)
    position: int | None = Field(default=None, ge=0, le=9999)
    unassign: bool = False


@app.get("/api/config")
def get_config(who: Identity = Depends(identity)):
    with db.session(who.user_id) as conn:
        cats = repo.list_categories(conn)
        chores = repo.list_chores(conn)
    by_cat: dict[int, list] = {}
    for c in chores:
        by_cat.setdefault(c["category_id"], []).append(
            {
                "id": c["id"],
                "text": c["text"],
                "assignee": c["assignee"],
                "position": c["position"],
            }
        )
    return {
        "may_write": who.may_write,
        "cycles": list(cycles.CYCLES),
        "categories": [
            {
                "id": c["id"],
                "name": c["name"],
                "cycle": c["cycle"],
                "descriptor": c["descriptor"],
                "position": c["position"],
                "chores": by_cat.get(c["id"], []),
            }
            for c in cats
        ],
    }


@app.post("/api/config/categories", status_code=201)
def create_category(body: CategoryIn, who: Identity = Depends(identity)):
    require_write(who)
    with db.session(who.user_id) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chore_categories"
            " (household_id, name, cycle, descriptor, position, created_by)"
            " VALUES (%s, %s, %s, %s,"
            "   (SELECT coalesce(max(position) + 1, 0) FROM chore_categories"
            "     WHERE household_id = %s), %s)"
            " RETURNING id, name, cycle, descriptor, position",
            (
                config.HOUSEHOLD_ID,
                body.name,
                body.cycle,
                body.descriptor,
                config.HOUSEHOLD_ID,
                who.user_id,
            ),
        )
        row = cur.fetchone()
    jlog("category.create", category_id=row["id"])
    return row


@app.patch("/api/config/categories/{category_id}")
def update_category(category_id: int, body: CategoryPatch, who: Identity = Depends(identity)):
    require_write(who)
    sets, params = [], []
    for field in ("name", "cycle", "descriptor", "position"):
        value = getattr(body, field)
        if value is not None:
            sets.append(f"{field} = %s")
            params.append(value)
    if not sets:
        raise HTTPException(status_code=400, detail="nothing to update")
    params += [config.HOUSEHOLD_ID, category_id]
    with db.session(who.user_id) as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE chore_categories SET {', '.join(sets)}"
            " WHERE household_id = %s AND id = %s AND archived_at IS NULL"
            " RETURNING id, name, cycle, descriptor, position",
            params,
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="category not found")
    jlog("category.update", category_id=category_id)
    return row


@app.delete("/api/config/categories/{category_id}")
def archive_category(category_id: int, who: Identity = Depends(identity)):
    """Soft delete. The completion log keeps referring to it, so rows never vanish."""
    require_write(who)
    with db.session(who.user_id) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chore_categories SET archived_at = now()"
            " WHERE household_id = %s AND id = %s AND archived_at IS NULL RETURNING id",
            (config.HOUSEHOLD_ID, category_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="category not found")
        cur.execute(
            "UPDATE chores SET archived_at = now()"
            " WHERE household_id = %s AND category_id = %s AND archived_at IS NULL",
            (config.HOUSEHOLD_ID, category_id),
        )
    jlog("category.archive", category_id=category_id)
    return {"archived": category_id}


@app.post("/api/config/chores", status_code=201)
def create_chore(body: ChoreIn, who: Identity = Depends(identity)):
    require_write(who)
    with db.session(who.user_id) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM chore_categories"
            " WHERE household_id = %s AND id = %s AND archived_at IS NULL",
            (config.HOUSEHOLD_ID, body.category_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="category not found")
        cur.execute(
            "INSERT INTO chores"
            " (household_id, category_id, text, assignee, position, created_by)"
            " VALUES (%s, %s, %s, %s,"
            "   (SELECT coalesce(max(position) + 1, 0) FROM chores"
            "     WHERE household_id = %s AND category_id = %s), %s)"
            " RETURNING id, category_id, text, assignee, position",
            (
                config.HOUSEHOLD_ID,
                body.category_id,
                body.text,
                body.assignee or None,
                config.HOUSEHOLD_ID,
                body.category_id,
                who.user_id,
            ),
        )
        row = cur.fetchone()
    jlog("chore.create", chore_id=row["id"])
    return row


@app.patch("/api/config/chores/{chore_id}")
def update_chore(chore_id: int, body: ChorePatch, who: Identity = Depends(identity)):
    require_write(who)
    sets, params = [], []
    if body.unassign:
        sets.append("assignee = NULL")
    elif body.assignee is not None:
        sets.append("assignee = %s")
        params.append(body.assignee or None)
    for field in ("category_id", "text", "position"):
        value = getattr(body, field)
        if value is not None:
            sets.append(f"{field} = %s")
            params.append(value)
    if not sets:
        raise HTTPException(status_code=400, detail="nothing to update")

    with db.session(who.user_id) as conn, conn.cursor() as cur:
        if body.category_id is not None:
            cur.execute(
                "SELECT 1 FROM chore_categories"
                " WHERE household_id = %s AND id = %s AND archived_at IS NULL",
                (config.HOUSEHOLD_ID, body.category_id),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="category not found")
        cur.execute(
            f"UPDATE chores SET {', '.join(sets)}"
            " WHERE household_id = %s AND id = %s AND archived_at IS NULL"
            " RETURNING id, category_id, text, assignee, position",
            params + [config.HOUSEHOLD_ID, chore_id],
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="chore not found")
    jlog("chore.update", chore_id=chore_id)
    return row


@app.delete("/api/config/chores/{chore_id}")
def archive_chore(chore_id: int, who: Identity = Depends(identity)):
    require_write(who)
    with db.session(who.user_id) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chores SET archived_at = now()"
            " WHERE household_id = %s AND id = %s AND archived_at IS NULL RETURNING id",
            (config.HOUSEHOLD_ID, chore_id),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="chore not found")
    jlog("chore.archive", chore_id=chore_id)
    return {"archived": chore_id}


# ---------------------------------------------------------------- static

@app.get("/")
def index():
    return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=config.WEB_DIST), name="static")
