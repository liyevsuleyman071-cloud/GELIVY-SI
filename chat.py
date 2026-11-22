import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bot import bot
from core import (
    get_chat,
    list_chats,
    page_context,
    parse_uuid,
    require_user,
    supabase,
    templates,
)

logger = logging.getLogger("gelivyai.chat")

router = APIRouter(prefix="/chat", tags=["Chat"])

MAX_MESSAGE_LEN = 2000
TITLE_LEN = 40

# Qeyd: route-lar "def"-dir. Supabase və bot sinxrondur; FastAPI "def" route-ları
# thread pool-da işlədir, beləcə server digər sorğulara cavab verməyə davam edir.
#
# Axın (HTMX, 2 mərhələ):
#   1) POST /chat/{id}/send  -> istifadəçi mesajı saxlanır, dərhal "yazır..." göstəricisi qayıdır
#   2) POST /chat/{id}/reply -> (göstərici özü yüklənəndə çağırır) AI cavabı hazırlanıb saxlanır


@router.get("")
def new_chat(user: dict = Depends(require_user)):
    # Bazaya yazmırıq: söhbət ilk mesaj göndəriləndə yaranır.
    return RedirectResponse(f"/chat/{uuid.uuid4()}", status_code=303)


@router.get("/{chat_id}", response_class=HTMLResponse)
def chat_page(request: Request, chat_id: str, user: dict = Depends(require_user)):
    cid = parse_uuid(chat_id)
    if not cid:
        return RedirectResponse("/chat", status_code=303)

    chat = get_chat(user["id"], cid)
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context=page_context(
            user,
            title="Gelivy AI",
            page="chat",
            chat_id=cid,
            chat_title=chat["title"] if chat else "Yeni söhbət",
            messages=chat["messages"] if chat else [],
        ),
    )


@router.post("/{chat_id}/send", response_class=HTMLResponse)
def send_message(
    request: Request,
    chat_id: str,
    message: str = Form(...),
    user: dict = Depends(require_user),
):
    cid = parse_uuid(chat_id)
    text = message.strip()[:MAX_MESSAGE_LEN]
    if not cid or not text:
        return HTMLResponse("")

    item = {"role": "human", "content": text}
    chat = get_chat(user["id"], cid)
    is_new = chat is None

    if is_new:
        (
            supabase.table("chats")
            .insert(
                {
                    "id": cid,
                    "user_id": str(user["id"]),
                    "title": text[:TITLE_LEN],
                    "messages": [item],  # jsonb: json.dumps lazım deyil
                }
            )
            .execute()
        )
    else:
        (
            supabase.table("chats")
            .update({"messages": chat["messages"] + [item]})
            .eq("id", cid)
            .eq("user_id", str(user["id"]))
            .execute()
        )

    context = {"message": text, "chat_id": cid, "oob": True}
    if is_new:
        # Yeni söhbət sidebar siyahısına HTMX out-of-band swap ilə əlavə olunur.
        context["chats"] = list_chats(user["id"])
        context["new_chat"] = True

    return templates.TemplateResponse(
        request=request, name="partials/send_response.html", context=context
    )


@router.post("/{chat_id}/reply", response_class=HTMLResponse)
def reply(request: Request, chat_id: str, user: dict = Depends(require_user)):
    cid = parse_uuid(chat_id)
    chat = get_chat(user["id"], cid) if cid else None
    history = chat["messages"] if chat else []

    # Cavab veriləcək istifadəçi mesajı yoxdursa (məs. təkrar sorğu) heç nə etmirik.
    if not history or history[-1].get("role") != "human":
        return HTMLResponse("")

    try:
        answer = bot.ask_ai(history)
        if not answer:
            raise ValueError("Boş cavab")
    except Exception:
        logger.exception("AI cavabı alınmadı (chat_id=%s)", cid)
        return templates.TemplateResponse(
            request=request, name="partials/reply_error.html", context={"chat_id": cid}
        )

    (
        supabase.table("chats")
        .update({"messages": history + [{"role": "ai", "content": answer}]})
        .eq("id", cid)
        .eq("user_id", str(user["id"]))
        .execute()
    )
    return templates.TemplateResponse(
        request=request, name="partials/ai_bubble.html", context={"content": answer}
    )


@router.delete("/{chat_id}", response_class=HTMLResponse)
def delete_chat(request: Request, chat_id: str, user: dict = Depends(require_user)):
    cid = parse_uuid(chat_id)
    if cid:
        (
            supabase.table("chats")
            .delete()
            .eq("id", cid)
            .eq("user_id", str(user["id"]))
            .execute()
        )

    # Açıq olan söhbət silinibsə yeni söhbətə keçirik, əks halda siyahıdan sadəcə çıxarırıq.
    if cid and cid in request.headers.get("HX-Current-URL", ""):
        return HTMLResponse("", headers={"HX-Redirect": "/chat"})
    return HTMLResponse("")
