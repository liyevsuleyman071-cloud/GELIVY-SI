import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core import META_APP_SECRET, VERIFY_TOKEN

logger = logging.getLogger("gelivyai.webhook")

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# Meta eyni ünvanı həm təsdiq (GET), həm də hadisələr (POST) üçün çağırır.
# "" və "/" hər ikisi qeydə alınıb ki, yönləndirmə (redirect) olmadan işləsin.
@router.get("")
@router.get("/", include_in_schema=False)
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if (
        mode == "subscribe"
        and VERIFY_TOKEN
        and token
        and hmac.compare_digest(token, VERIFY_TOKEN)
        and challenge
    ):
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
@router.post("/", include_in_schema=False)
async def receive_message(request: Request):
    body = await request.body()

    # META_APP_SECRET təyin olunubsa Meta-nın imzasını yoxlayırıq.
    if META_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(META_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        data = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Instagram webhook event received: object=%s", data.get("object"))
    return {"status": "received"}
