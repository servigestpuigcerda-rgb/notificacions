"""Comprueba qué permisos de correo lleva un token delegado de Microsoft Graph.

Uso:  python -m servigest_correo.permisos <access_token>
(o importa `permisos_correo(token)` desde el servidor y llámalo al arrancar / en un endpoint de diagnóstico).
No valida la firma: solo lee el claim `scp` para diagnosticar.
"""
import base64
import json
import sys


def scopes_del_token(token: str) -> set[str]:
    carga = token.split(".")[1]
    carga += "=" * (-len(carga) % 4)
    datos = json.loads(base64.urlsafe_b64decode(carga))
    return set((datos.get("scp") or "").split())


def permisos_correo(token: str) -> str:
    scp = scopes_del_token(token)
    if "Mail.ReadWrite" in scp:
        return "OK: el token tiene Mail.ReadWrite (buscar y mover correos funcionará)."
    if "Mail.Read" in scp:
        return ("FALTA Mail.ReadWrite: el token solo tiene Mail.Read. buscar_correos funciona, "
                "mover_correo fallará. Añade el permiso delegado Mail.ReadWrite en Azure y concede consentimiento.")
    return f"El token no tiene permisos de correo. Scopes: {', '.join(sorted(scp)) or '(ninguno)'}"


if __name__ == "__main__":
    print(permisos_correo(sys.argv[1]))
