from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.all_models import User
from app.services.llm_service import llm_service

router = APIRouter(prefix="/llm", tags=["Local LLM (Ollama)"])

@router.get("/status")
async def get_ollama_status(_: User = Depends(get_current_user)):
    status = await llm_service.check_ollama_status()
    return status
