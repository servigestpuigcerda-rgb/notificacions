"""Usuaris i sessions (galeta HttpOnly)."""
import hashlib
import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request

from . import db

COOKIE = "gestio_sessio"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(calc.hex(), h)


def hi_ha_usuaris() -> bool:
    return bool(db.scalar("SELECT COUNT(*) FROM usuaris"))


def crear_usuari(nom, usuari, password, rol="admin", cost_hora=0, preu_hora=0) -> int:
    if len(password or "") < 8:
        raise HTTPException(400, "La contrasenya ha de tenir com a mínim 8 caràcters.")
    if db.scalar("SELECT 1 FROM usuaris WHERE usuari = ?", (usuari,)):
        raise HTTPException(400, "Aquest nom d'usuari ja existeix.")
    return db.insert("usuaris", {"nom": nom, "usuari": usuari, "password_hash": hash_password(password),
                                 "rol": rol, "cost_hora": cost_hora, "preu_hora": preu_hora, "created_at": db.now()})


def login(usuari: str, password: str) -> str | None:
    u = db.row("SELECT * FROM usuaris WHERE usuari = ? AND actiu = 1", (usuari,))
    if not u or not check_password(password, u["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    db.insert("sessions", {"token": token, "usuari_id": u["id"], "created_at": db.now()})
    return token


def logout(token: str):
    with db.tx() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def usuari_actual(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Cal iniciar sessió.")
    u = db.row("SELECT u.id, u.nom, u.usuari, u.rol, u.cost_hora, u.preu_hora FROM sessions s "
               "JOIN usuaris u ON u.id = s.usuari_id WHERE s.token = ? AND u.actiu = 1", (token,))
    if not u:
        raise HTTPException(401, "Sessió caducada.")
    return u


def admin(u: dict = Depends(usuari_actual)) -> dict:
    if u["rol"] != "admin":
        raise HTTPException(403, "Només l'administrador pot fer això.")
    return u
