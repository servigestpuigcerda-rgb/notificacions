#!/usr/bin/env python3
"""
Integració amb Microsoft Planner via Microsoft Graph API.
Crea una tasca al Planner amb la llista de la compra.
"""

import os
import json
import requests
from datetime import datetime, timezone


def obtenir_token(tenant_id, client_id, client_secret):
    """Obté un token d'accés de Microsoft Identity Platform."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def crear_tasca_planner(productes_afegits, productes_saltats=None):
    """
    Crea una tasca a Microsoft Planner amb la llista de la compra.

    Retorna True si s'ha creat correctament, False si no hi ha configuració
    o si hi ha un error.
    """
    tenant_id = os.getenv("PLANNER_TENANT_ID", "")
    client_id = os.getenv("PLANNER_CLIENT_ID", "")
    client_secret = os.getenv("PLANNER_CLIENT_SECRET", "")
    plan_id = os.getenv("PLANNER_PLAN_ID", "")
    bucket_id = os.getenv("PLANNER_BUCKET_ID", "")  # opcional

    if not all([tenant_id, client_id, client_secret, plan_id]):
        return False

    try:
        token = obtenir_token(tenant_id, client_id, client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        data = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
        titol = f"Compra BonpreuEsclat — {data}"

        # Cos de la nota amb la llista de productes
        lines = []
        if productes_afegits:
            lines.append("PRODUCTES AL CARRO:")
            for p in productes_afegits:
                lines.append(f"• {p}")
        if productes_saltats:
            lines.append("")
            lines.append("SALTATS:")
            for p in productes_saltats:
                lines.append(f"• {p}")

        # Crear la tasca
        tasca_payload = {
            "planId": plan_id,
            "title": titol,
        }
        if bucket_id:
            tasca_payload["bucketId"] = bucket_id

        resp = requests.post(
            "https://graph.microsoft.com/v1.0/planner/tasks",
            headers=headers,
            json=tasca_payload,
            timeout=10,
        )
        resp.raise_for_status()
        tasca_id = resp.json()["id"]
        etag = resp.json()["@odata.etag"]

        # Afegir detalls (notes) a la tasca
        if lines:
            cos = "\n".join(lines)
            detalls_payload = {
                "description": cos,
            }
            requests.patch(
                f"https://graph.microsoft.com/v1.0/planner/tasks/{tasca_id}/details",
                headers={**headers, "If-Match": etag},
                json=detalls_payload,
                timeout=10,
            )

        print(f"\n  Tasca creada a Microsoft Planner: '{titol}'")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"\n  Error creant tasca al Planner: {e.response.status_code} {e.response.text}")
        return False
    except Exception as e:
        print(f"\n  Error connectant amb Microsoft Planner: {e}")
        return False
