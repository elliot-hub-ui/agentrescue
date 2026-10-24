"""Test-only Stripe Checkout for prepaid, one-diagnosis tokens.

This deliberately accepts test keys only. Stripe's signed webhook, rather than
the browser redirect, activates a one-use bearer token after payment succeeds.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

PRICE_CENTS = 100


class StripeConfigError(RuntimeError):
    pass


def stripe_settings(env=None):
    env = os.environ if env is None else env
    if env.get("AGENTRESCUE_STRIPE_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return None
    key = env.get("STRIPE_SECRET_KEY", "").strip()
    if not (key.startswith("sk_test_") or key.startswith("rk_test_")):
        raise StripeConfigError("Stripe Checkout test mode requires an sk_test_ or rk_test_ secret key")
    webhook_secret = env.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret.startswith("whsec_"):
        raise StripeConfigError("Stripe Checkout test mode requires a whsec_ webhook signing secret")
    base_url = env.get("AGENTRESCUE_PUBLIC_URL", "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise StripeConfigError("AGENTRESCUE_PUBLIC_URL must be an https URL")
    db_path = env.get("AGENTRESCUE_STRIPE_DB", "data/stripe.sqlite3").strip()
    if not db_path:
        raise StripeConfigError("AGENTRESCUE_STRIPE_DB must be a non-empty path")
    return {"key": key, "webhook_secret": webhook_secret, "base_url": base_url, "db_path": db_path}


def _connect(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS diagnosis_tokens (
            token_hash TEXT PRIMARY KEY,
            session_id TEXT UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('pending', 'paid', 'used')),
            created_at INTEGER NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS stripe_events (
            event_id TEXT PRIMARY KEY,
            received_at INTEGER NOT NULL
        )
    """)
    return connection


def _create_checkout(settings, token_hash):
    from stripe import StripeClient

    client = StripeClient(settings["key"])
    suffix = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
    session = client.v1.checkout.sessions.create(params={
        "mode": "payment",
        "ui_mode": "hosted_page",
        "line_items": [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "AgentRescue one diagnosis (sandbox test)"},
                "unit_amount": PRICE_CENTS,
            },
            "quantity": 1,
        }],
        "client_reference_id": token_hash,
        "metadata": {"agentrescue_token_hash": token_hash, "environment": "test"},
        "success_url": settings["base_url"] + "/stripe/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": settings["base_url"] + "/stripe/cancel",
        "integration_identifier": "agentrescue_test_" + suffix,
    })
    return session


async def checkout(request: Request):
    try:
        settings = stripe_settings()
    except StripeConfigError as exc:
        return JSONResponse({"error": "stripe_configuration_invalid", "detail": str(exc)}, status_code=503)
    if settings is None:
        return JSONResponse({"error": "stripe_test_payments_disabled"}, status_code=404)
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    connection = _connect(settings["db_path"])
    try:
        connection.execute(
            "INSERT INTO diagnosis_tokens(token_hash, status, created_at) VALUES (?, 'pending', ?)",
            (token_hash, int(time.time())),
        )
        try:
            session = _create_checkout(settings, token_hash)
        except Exception:
            connection.execute("DELETE FROM diagnosis_tokens WHERE token_hash = ?", (token_hash,))
            return JSONResponse({"error": "stripe_checkout_unavailable"}, status_code=502)
        if not isinstance(session, dict) or not session.get("id") or not session.get("url"):
            connection.execute("DELETE FROM diagnosis_tokens WHERE token_hash = ?", (token_hash,))
            return JSONResponse({"error": "stripe_checkout_unavailable"}, status_code=502)
        connection.execute("UPDATE diagnosis_tokens SET session_id = ? WHERE token_hash = ?", (session["id"], token_hash))
    finally:
        connection.close()
    return JSONResponse({
        "checkout_url": session["url"],
        "access_token": token,
        "price_usd": "1.00",
        "mode": "test",
        "instructions": "Complete test Checkout, then use this bearer token once at /v1/stripe/diagnose. The token stays pending until a signed Stripe webhook confirms payment.",
    }, status_code=201, headers={"Cache-Control": "no-store"})


def _verify_signature(payload: bytes, signature: str, secret: str, now=None):
    parts = {}
    for item in signature.split(","):
        key, separator, value = item.partition("=")
        if separator:
            parts.setdefault(key, []).append(value)
    timestamp = (parts.get("t") or [""])[0]
    if not timestamp.isdecimal() or abs((int(time.time()) if now is None else now) - int(timestamp)) > 300:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", []))


async def webhook(request: Request):
    try:
        settings = stripe_settings()
    except StripeConfigError:
        return JSONResponse({"error": "stripe_configuration_invalid"}, status_code=503)
    if settings is None:
        return JSONResponse({"error": "stripe_test_payments_disabled"}, status_code=404)
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    if len(payload) > 65536 or not _verify_signature(payload, signature, settings["webhook_secret"]):
        return JSONResponse({"error": "invalid_signature"}, status_code=400)
    try:
        event = json.loads(payload)
        event_id = event["id"]
        event_type = event["type"]
        session = event["data"]["object"]
    except (ValueError, TypeError, KeyError):
        return JSONResponse({"error": "invalid_event"}, status_code=400)
    connection = _connect(settings["db_path"])
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM stripe_events WHERE event_id = ?", (event_id,)).fetchone():
            connection.commit()
            return JSONResponse({"received": True, "duplicate": True})
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            token_hash = (session.get("metadata") or {}).get("agentrescue_token_hash")
            valid = (
                session.get("mode") == "payment"
                and session.get("payment_status") == "paid"
                and session.get("currency") == "usd"
                and session.get("amount_total") == PRICE_CENTS
                and session.get("livemode") is False
                and bool(token_hash)
            )
            if valid:
                connection.execute(
                    "UPDATE diagnosis_tokens SET status = 'paid' WHERE token_hash = ? AND session_id = ? AND status = 'pending'",
                    (token_hash, session.get("id")),
                )
        connection.execute("INSERT INTO stripe_events(event_id, received_at) VALUES (?, ?)", (event_id, int(time.time())))
        connection.commit()
    except Exception:
        connection.rollback()
        return JSONResponse({"error": "webhook_processing_failed"}, status_code=500)
    finally:
        connection.close()
    return JSONResponse({"received": True})


async def paid_diagnose(request: Request):
    try:
        settings = stripe_settings()
    except StripeConfigError:
        return JSONResponse({"error": "stripe_configuration_invalid"}, status_code=503)
    if settings is None:
        return JSONResponse({"error": "stripe_test_payments_disabled"}, status_code=404)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse({"error": "bearer_token_required"}, status_code=401)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(body, dict) or set(body) - {"error", "system"}:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    error = body.get("error")
    system = body.get("system", "http")
    from app import MAX_DIAGNOSIS_CHARS, VALID_SYSTEMS, diagnose
    if not isinstance(error, str) or not error.strip():
        return JSONResponse({"error": "error_required"}, status_code=400)
    if len(error) > MAX_DIAGNOSIS_CHARS:
        return JSONResponse({"error": "diagnostic_too_large", "max_chars": MAX_DIAGNOSIS_CHARS}, status_code=413)
    if not isinstance(system, str) or system not in VALID_SYSTEMS:
        return JSONResponse({"error": "invalid_system", "allowed": sorted(VALID_SYSTEMS)}, status_code=400)
    connection = _connect(settings["db_path"])
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT status FROM diagnosis_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        if not row or row["status"] != "paid":
            connection.rollback()
            return JSONResponse({"error": "payment_required"}, status_code=402)
        changed = connection.execute(
            "UPDATE diagnosis_tokens SET status = 'used' WHERE token_hash = ? AND status = 'paid'",
            (token_hash,),
        ).rowcount
        if changed != 1:
            connection.rollback()
            return JSONResponse({"error": "payment_required"}, status_code=402)
        connection.commit()
    finally:
        connection.close()
    return JSONResponse(diagnose(error, system))


async def success(request: Request):
    return PlainTextResponse("Stripe test payment return received. Access is granted only after the signed webhook; return here does not prove payment.")


async def cancel(request: Request):
    return PlainTextResponse("Stripe test Checkout was cancelled. No diagnosis credit was used.")
