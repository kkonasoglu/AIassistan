"""Admin paneli uç noktaları. Hepsi admin gerektirir; kurallar (son admin vb.)
users.py servisinde uygulanır, burada sadece HTTP'ye çevrilir."""
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.auth import map_errors, user_json
from app.api.deps import require_admin
from app.services import knowledge, rag, sessions, users
from app.services.users import User

router = APIRouter(prefix="/admin")


class NewUser(BaseModel):
    username: str
    password: str
    role: str = "user"


class RoleBody(BaseModel):
    role: str


class ActiveBody(BaseModel):
    active: bool


class PasswordBody(BaseModel):
    password: str


class TransferBody(BaseModel):
    target_id: int


class KnowledgeBody(BaseModel):
    title: str
    solution: str


class QuestionBody(BaseModel):
    question: str


@router.get("/users")
@map_errors
def list_users(admin: User = Depends(require_admin)):
    return [user_json(u) for u in users.list_users(admin.id)]


@router.post("/users")
@map_errors
def create_user(body: NewUser, admin: User = Depends(require_admin)):
    return user_json(users.create_user(body.username, body.password, body.role, admin.id))


@router.patch("/users/{user_id}/role")
@map_errors
def set_role(user_id: int, body: RoleBody, admin: User = Depends(require_admin)):
    users.set_role(admin.id, user_id, body.role)
    return {"ok": True}


@router.patch("/users/{user_id}/active")
@map_errors
def set_active(user_id: int, body: ActiveBody, admin: User = Depends(require_admin)):
    users.set_active(admin.id, user_id, body.active)
    if not body.active:
        sessions.destroy_all_for_user(user_id)
    return {"ok": True}


@router.post("/users/{user_id}/password")
@map_errors
def reset_password(user_id: int, body: PasswordBody, admin: User = Depends(require_admin)):
    users.change_password(admin.id, user_id, body.password)
    if user_id != admin.id:
        sessions.destroy_all_for_user(user_id)
    return {"ok": True}


@router.post("/transfer")
@map_errors
def transfer(body: TransferBody, admin: User = Depends(require_admin)):
    users.transfer_admin(admin.id, body.target_id)
    return {"ok": True}


# ---------------- Bilgi bankası yönetimi ----------------
# Not: /knowledge/export ve /knowledge/test, /knowledge/{id} yollarından ÖNCE tanımlıdır.

@router.get("/knowledge")
@map_errors
def list_knowledge(deleted: bool = False, admin: User = Depends(require_admin)):
    """deleted=true: silinenler de listelenir."""
    return knowledge.list_all(include_deleted=deleted)


@router.get("/knowledge/export")
@map_errors
def export_knowledge(admin: User = Depends(require_admin)):
    """Tüm kayıtları (silinenler dahil) JSON olarak indirir: yedek / taşıma için."""
    data = knowledge.export_all()
    name = f"bilgi-bankasi-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/knowledge/test")
@map_errors
def test_search(body: QuestionBody, admin: User = Depends(require_admin)):
    """Arama testi: bir soru için hangi kayıtlar hangi mesafeyle bulunur?"""
    return rag.debug_search(body.question)


@router.post("/knowledge")
@map_errors
def add_knowledge(body: KnowledgeBody, admin: User = Depends(require_admin)):
    return {"id": knowledge.add(body.title, body.solution, admin.username)}


@router.put("/knowledge/{record_id}")
@map_errors
def update_knowledge(record_id: str, body: KnowledgeBody, admin: User = Depends(require_admin)):
    knowledge.update(record_id, body.title, body.solution, admin.username)
    return {"ok": True}


@router.delete("/knowledge/{record_id}")
@map_errors
def delete_knowledge(record_id: str, admin: User = Depends(require_admin)):
    knowledge.delete(record_id, admin.username)
    return {"ok": True}


@router.post("/knowledge/{record_id}/restore")
@map_errors
def restore_knowledge(record_id: str, admin: User = Depends(require_admin)):
    knowledge.restore(record_id, admin.username)
    return {"ok": True}
