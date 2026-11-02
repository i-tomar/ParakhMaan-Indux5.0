from fastapi import APIRouter, Body, Depends
from app.api.deps import get_current_user
from app.models.all_models import User
from app.services.rag_service import rag_service

router = APIRouter(prefix="/rag", tags=["RAG Legal Assistant"])

@router.post("/ask")
def ask_rule_book(payload: dict = Body(...), _: User = Depends(get_current_user)):
    # The frontend sends "query"; "question" is accepted for API clients.
    question = str(payload.get("question") or payload.get("query") or "").strip()[:2000]
    if not question:
        return {"error": "Question cannot be empty", "answer": "", "citations": []}
    
    result = rag_service.query(question)
    return result
