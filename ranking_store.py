#!/usr/bin/env python3
"""
Storage astratto per il ranking settimanale.

Due backend intercambiabili:
  - FirestoreRankingStore: persistenza reale su Firebase Firestore (consigliato in
    produzione: sopravvive ai redeploy/restart del container su Render).
  - JsonRankingStore: fallback su file locale (sviluppo locale o assenza di
    credenziali Firebase). NB: su filesystem effimero non sopravvive ai redeploy.

La scelta del backend e' automatica: se le credenziali Firebase sono presenti si usa
Firestore, altrimenti si ripiega sul JSON. L'interfaccia e' asincrona e le operazioni
di rete/IO girano in un thread separato per non bloccare l'event loop del bot.

Credenziali Firebase accettate (in ordine di priorita'):
  - env FIREBASE_CREDENTIALS_JSON  -> contenuto JSON del service account
  - env FIREBASE_CREDENTIALS_FILE / GOOGLE_APPLICATION_CREDENTIALS -> path al file
  - /etc/secrets/firebase_credentials.json  (Render Secret File di default)
"""

import os
import json
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class RankingStore:
    """Interfaccia comune."""

    async def add_point(self, user_id: int) -> None:
        raise NotImplementedError

    async def get_all(self) -> Dict[int, int]:
        raise NotImplementedError

    async def reset(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Backend: file JSON locale
# ---------------------------------------------------------------------------

class JsonRankingStore(RankingStore):
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[int, int] = self._load()
        logger.info(f"Ranking: backend JSON locale ({self.path}, {len(self.data)} utenti)")

    def _load(self) -> Dict[int, int]:
        out: Dict[int, int] = {}
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for k, v in raw.items():
                    try:
                        out[int(k)] = int(v)
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            logger.warning(f"Ranking JSON: load fallito: {e}")
        return out

    def _save(self) -> None:
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({str(k): v for k, v in self.data.items()}, f)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"Ranking JSON: save fallito: {e}")

    async def add_point(self, user_id: int) -> None:
        self.data[user_id] = self.data.get(user_id, 0) + 1
        await asyncio.to_thread(self._save)

    async def get_all(self) -> Dict[int, int]:
        return dict(self.data)

    async def reset(self) -> None:
        self.data = {}
        await asyncio.to_thread(self._save)


# ---------------------------------------------------------------------------
# Backend: Firebase Firestore
# ---------------------------------------------------------------------------

class FirestoreRankingStore(RankingStore):
    def __init__(self, client):
        from firebase_admin import firestore
        self._firestore = firestore
        # Documento unico: bot_state/weekly_ranking con campo mappa "counts"
        self._doc = client.collection('bot_state').document('weekly_ranking')
        logger.info("Ranking: backend Firebase Firestore attivo")

    async def add_point(self, user_id: int) -> None:
        def _op():
            # Increment atomico sul campo annidato counts.<user_id>
            self._doc.set(
                {'counts': {str(user_id): self._firestore.Increment(1)}},
                merge=True,
            )
        await asyncio.to_thread(_op)

    async def get_all(self) -> Dict[int, int]:
        def _op():
            snap = self._doc.get()
            if not snap.exists:
                return {}
            return (snap.to_dict() or {}).get('counts', {}) or {}
        raw = await asyncio.to_thread(_op)
        out: Dict[int, int] = {}
        for k, v in raw.items():
            try:
                out[int(k)] = int(v)
            except (ValueError, TypeError):
                continue
        return out

    async def reset(self) -> None:
        def _op():
            self._doc.set({'counts': {}})
        await asyncio.to_thread(_op)


# ---------------------------------------------------------------------------
# Inizializzazione Firebase + factory
# ---------------------------------------------------------------------------

def _init_firestore_client():
    """Ritorna un client Firestore se le credenziali sono disponibili, altrimenti None."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        logger.info("Ranking: firebase-admin non installato, uso fallback JSON")
        return None

    cred = None
    try:
        cred_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
        cred_file = (
            os.getenv('FIREBASE_CREDENTIALS_FILE')
            or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        )
        default_secret = '/etc/secrets/firebase_credentials.json'

        if cred_json and cred_json.strip():
            cred = credentials.Certificate(json.loads(cred_json))
        elif cred_file and os.path.exists(cred_file):
            cred = credentials.Certificate(cred_file)
        elif os.path.exists(default_secret):
            cred = credentials.Certificate(default_secret)
    except Exception as e:
        logger.error(f"Ranking: credenziali Firebase non valide: {e}")
        return None

    if cred is None:
        logger.info("Ranking: nessuna credenziale Firebase trovata, uso fallback JSON")
        return None

    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        logger.error(f"Ranking: inizializzazione Firebase fallita: {e}")
        return None


def get_ranking_store(json_fallback_path: str) -> RankingStore:
    """Crea lo store: Firestore se possibile, altrimenti JSON locale."""
    client = _init_firestore_client()
    if client is not None:
        try:
            return FirestoreRankingStore(client)
        except Exception as e:
            logger.error(f"Ranking: Firestore non utilizzabile, fallback JSON: {e}")
    return JsonRankingStore(json_fallback_path)
