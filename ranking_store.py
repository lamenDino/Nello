#!/usr/bin/env python3
"""
Storage del ranking + statistiche del bot.

Tiene tre classifiche (settimanale / mensile / all-time), una cache dei nomi
utente, gli achievement gia' assegnati e una memoria dei link recenti (per il
rilevamento "gia' postato"). La settimanale viene azzerata dal job del sabato;
la mensile si azzera da sola al cambio di mese; l'all-time non si azzera mai.

Due backend intercambiabili:
  - FirestoreRankingStore: persistenza reale su Firebase (consigliato in prod).
  - JsonRankingStore: fallback su file locale (sviluppo / assenza credenziali).

Interfaccia asincrona; le operazioni di IO/rete girano in un thread separato.
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import pytz
    _TZ = pytz.timezone('Europe/Rome')
except Exception:
    _TZ = None

logger = logging.getLogger(__name__)

# Soglie achievement (numero di contenuti all-time) -> codice
MILESTONES = [(10, 'm10'), (50, 'm50'), (100, 'm100'), (250, 'm250'),
              (500, 'm500'), (1000, 'm1000')]

# Limiti memoria link recenti
RECENT_MAX = 400
RECENT_TTL = 14 * 24 * 3600  # 14 giorni

# Cache file_id Telegram (per rinviare un media gia' caricato senza riscaricarlo)
CACHE_MAX = 800
CACHE_TTL = 30 * 24 * 3600  # 30 giorni


def _now():
    return datetime.now(_TZ) if _TZ else datetime.now()


def _month_key() -> str:
    n = _now()
    return f"{n.year}-{n.month:02d}"


class RankingStore:
    async def add_point(self, user_id: int, name: str) -> Dict[str, int]:
        raise NotImplementedError

    async def get_board(self, period: str, limit: int = 10) -> List[Tuple[int, int, str]]:
        raise NotImplementedError

    async def get_user_stats(self, user_id: int) -> Dict:
        raise NotImplementedError

    async def reset_weekly(self) -> None:
        raise NotImplementedError

    async def get_earned(self, user_id: int) -> set:
        raise NotImplementedError

    async def add_earned(self, user_id: int, code: str) -> None:
        raise NotImplementedError

    async def check_link(self, key: str) -> Optional[Dict]:
        raise NotImplementedError

    async def record_link(self, key: str, user_id: int, name: str) -> None:
        raise NotImplementedError

    async def get_cached(self, key: str) -> Optional[Dict]:
        raise NotImplementedError

    async def set_cached(self, key: str, payload: Dict) -> None:
        raise NotImplementedError

    async def record_chat(self, chat_id: int, title: str) -> None:
        raise NotImplementedError

    async def get_chats(self) -> List[Dict]:
        raise NotImplementedError

    async def create_vote(self, vote_id: str, owner_id: int, owner_name: str) -> None:
        raise NotImplementedError

    async def toggle_vote(self, vote_id: str, voter_id: int) -> Optional[Dict]:
        raise NotImplementedError

    async def top_voted_week(self, limit: int = 3) -> List[Tuple[int, int, str]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Logica condivisa (pura) riutilizzata dai due backend
# ---------------------------------------------------------------------------

def _apply_point(data: dict, user_id: int, name: str) -> Dict[str, int]:
    """Incrementa weekly/monthly/alltime in `data` (dict di mappe). Gestisce il
    rollover mensile. Ritorna i nuovi totali."""
    uid = str(user_id)
    for k in ('weekly', 'monthly', 'alltime', 'names', 'earned'):
        data.setdefault(k, {})
    # Rollover mensile
    cur = _month_key()
    if data.get('month_key') != cur:
        data['monthly'] = {}
        data['month_key'] = cur
    for period in ('weekly', 'monthly', 'alltime'):
        data[period][uid] = int(data[period].get(uid, 0)) + 1
    if name:
        data['names'][uid] = name
    return {
        'weekly': data['weekly'][uid],
        'monthly': data['monthly'][uid],
        'alltime': data['alltime'][uid],
    }


def _build_board(data: dict, period: str, limit: int) -> List[Tuple[int, int, str]]:
    counts = data.get(period, {}) or {}
    names = data.get('names', {}) or {}
    rows = []
    for uid, cnt in counts.items():
        try:
            rows.append((int(uid), int(cnt), names.get(uid, 'Utente')))
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:limit]


def _user_stats(data: dict, user_id: int) -> Dict:
    uid = str(user_id)
    alltime = data.get('alltime', {}) or {}
    # rank all-time (1-based)
    ordered = sorted(alltime.items(), key=lambda x: int(x[1]), reverse=True)
    rank = next((i + 1 for i, (u, _c) in enumerate(ordered) if u == uid), None)
    return {
        'weekly': int((data.get('weekly', {}) or {}).get(uid, 0)),
        'monthly': int((data.get('monthly', {}) or {}).get(uid, 0)),
        'alltime': int(alltime.get(uid, 0)),
        'rank': rank,
        'total_users': len(alltime),
        'name': (data.get('names', {}) or {}).get(uid, 'Utente'),
    }


def _create_vote(votes: dict, vote_id: str, owner_id, owner_name: str):
    votes[vote_id] = {'o': str(owner_id), 'n': owner_name or 'Utente', 'v': [], 'c': 0, 't': time.time()}


def _toggle_vote(votes: dict, rankings: dict, vote_id: str, voter_id):
    rec = votes.get(vote_id)
    if not rec:
        return None  # record perso (video troppo vecchio)
    owner = str(rec.get('o'))
    if owner == str(voter_id):
        return {'self': True}
    voters = rec.setdefault('v', [])
    vid = str(voter_id)
    if vid in voters:
        voters.remove(vid)
        rec['c'] = max(0, int(rec.get('c', 1)) - 1)
        delta, voted = -1, False
    else:
        voters.append(vid)
        rec['c'] = int(rec.get('c', 0)) + 1
        delta, voted = 1, True
    vw = rankings.setdefault('vote_week', {})
    vw[owner] = max(0, int(vw.get(owner, 0)) + delta)
    return {'count': rec['c'], 'owner': owner, 'name': rec.get('n', 'Utente'), 'voted': voted}


def _top_voted(rankings: dict, limit: int):
    vw = rankings.get('vote_week', {}) or {}
    names = rankings.get('names', {}) or {}
    rows = []
    for k, v in vw.items():
        try:
            cnt = int(v)
        except (ValueError, TypeError):
            continue
        if cnt > 0:
            rows.append((int(k), cnt, names.get(k, 'Utente')))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:limit]


def _prune(d: dict, maxn: int, ttl: int) -> dict:
    now = time.time()
    items = [(k, v) for k, v in d.items()
             if isinstance(v, dict) and (now - float(v.get('t', 0))) < ttl]
    items.sort(key=lambda kv: float(kv[1].get('t', 0)), reverse=True)
    return dict(items[:maxn])


def _prune_recent(recent: dict) -> dict:
    return _prune(recent, RECENT_MAX, RECENT_TTL)


# ---------------------------------------------------------------------------
# Backend: file JSON locale
# ---------------------------------------------------------------------------

class JsonRankingStore(RankingStore):
    def __init__(self, path: str):
        self.path = path
        self.data = self._load()
        logger.info(f"Ranking: backend JSON locale ({self.path})")

    def _load(self) -> dict:
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Ranking JSON: load fallito: {e}")
        return {}

    def _save(self):
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"Ranking JSON: save fallito: {e}")

    async def add_point(self, user_id, name):
        totals = _apply_point(self.data, user_id, name)
        await asyncio.to_thread(self._save)
        return totals

    async def get_board(self, period, limit=10):
        return _build_board(self.data, period, limit)

    async def get_user_stats(self, user_id):
        return _user_stats(self.data, user_id)

    async def reset_weekly(self):
        self.data['weekly'] = {}
        self.data['vote_week'] = {}
        await asyncio.to_thread(self._save)

    async def get_earned(self, user_id):
        return set((self.data.get('earned', {}) or {}).get(str(user_id), []))

    async def add_earned(self, user_id, code):
        self.data.setdefault('earned', {})
        lst = self.data['earned'].setdefault(str(user_id), [])
        if code not in lst:
            lst.append(code)
            await asyncio.to_thread(self._save)

    async def check_link(self, key):
        return (self.data.get('recent', {}) or {}).get(key)

    async def record_link(self, key, user_id, name):
        self.data.setdefault('recent', {})
        self.data['recent'][key] = {'u': user_id, 'n': name, 't': time.time()}
        self.data['recent'] = _prune_recent(self.data['recent'])
        await asyncio.to_thread(self._save)

    async def get_cached(self, key):
        return (self.data.get('filecache', {}) or {}).get(key)

    async def set_cached(self, key, payload):
        self.data.setdefault('filecache', {})
        payload = dict(payload); payload['t'] = time.time()
        self.data['filecache'][key] = payload
        self.data['filecache'] = _prune(self.data['filecache'], CACHE_MAX, CACHE_TTL)
        await asyncio.to_thread(self._save)

    async def record_chat(self, chat_id, title):
        self.data.setdefault('chats', {})
        c = self.data['chats'].setdefault(str(chat_id), {'count': 0})
        c['title'] = title or c.get('title', '')
        c['count'] = int(c.get('count', 0)) + 1
        c['last'] = time.time()
        await asyncio.to_thread(self._save)

    async def get_chats(self):
        chats = self.data.get('chats', {}) or {}
        out = [{'id': k, **v} for k, v in chats.items()]
        out.sort(key=lambda x: x.get('count', 0), reverse=True)
        return out

    async def create_vote(self, vote_id, owner_id, owner_name):
        self.data.setdefault('votes', {})
        _create_vote(self.data['votes'], vote_id, owner_id, owner_name)
        self.data['votes'] = _prune(self.data['votes'], CACHE_MAX, CACHE_TTL)
        await asyncio.to_thread(self._save)

    async def toggle_vote(self, vote_id, voter_id):
        self.data.setdefault('votes', {})
        res = _toggle_vote(self.data['votes'], self.data, vote_id, voter_id)
        if res and not res.get('self'):
            await asyncio.to_thread(self._save)
        return res

    async def top_voted_week(self, limit=3):
        return _top_voted(self.data, limit)


# ---------------------------------------------------------------------------
# Backend: Firebase Firestore
# ---------------------------------------------------------------------------

class FirestoreRankingStore(RankingStore):
    def __init__(self, client):
        self._doc = client.collection('bot_state').document('rankings_v2')
        self._recent = client.collection('bot_state').document('recent_links')
        self._cache = client.collection('bot_state').document('file_cache')
        self._votes = client.collection('bot_state').document('votes')
        logger.info("Ranking: backend Firebase Firestore attivo")

    def _read(self) -> dict:
        snap = self._doc.get()
        return (snap.to_dict() or {}) if snap.exists else {}

    async def add_point(self, user_id, name):
        def _op():
            data = self._read()
            totals = _apply_point(data, user_id, name)
            self._doc.set(data)
            return totals
        return await asyncio.to_thread(_op)

    async def get_board(self, period, limit=10):
        data = await asyncio.to_thread(self._read)
        return _build_board(data, period, limit)

    async def get_user_stats(self, user_id):
        data = await asyncio.to_thread(self._read)
        return _user_stats(data, user_id)

    async def reset_weekly(self):
        def _op():
            self._doc.set({'weekly': {}, 'vote_week': {}}, merge=True)
        await asyncio.to_thread(_op)

    async def create_vote(self, vote_id, owner_id, owner_name):
        def _op():
            snap = self._votes.get()
            votes = (snap.to_dict() or {}) if snap.exists else {}
            _create_vote(votes, vote_id, owner_id, owner_name)
            votes = _prune(votes, CACHE_MAX, CACHE_TTL)
            self._votes.set(votes)
        await asyncio.to_thread(_op)

    async def toggle_vote(self, vote_id, voter_id):
        def _op():
            vsnap = self._votes.get()
            votes = (vsnap.to_dict() or {}) if vsnap.exists else {}
            rsnap = self._doc.get()
            rankings = (rsnap.to_dict() or {}) if rsnap.exists else {}
            res = _toggle_vote(votes, rankings, vote_id, voter_id)
            if res and not res.get('self'):
                self._votes.set(votes)
                self._doc.set({'vote_week': rankings.get('vote_week', {})}, merge=True)
            return res
        return await asyncio.to_thread(_op)

    async def top_voted_week(self, limit=3):
        data = await asyncio.to_thread(self._read)
        return _top_voted(data, limit)

    async def get_earned(self, user_id):
        data = await asyncio.to_thread(self._read)
        return set((data.get('earned', {}) or {}).get(str(user_id), []))

    async def add_earned(self, user_id, code):
        def _op():
            data = self._read()
            data.setdefault('earned', {})
            lst = data['earned'].setdefault(str(user_id), [])
            if code not in lst:
                lst.append(code)
                self._doc.set({'earned': {str(user_id): lst}}, merge=True)
        await asyncio.to_thread(_op)

    async def check_link(self, key):
        def _op():
            snap = self._recent.get()
            recent = (snap.to_dict() or {}) if snap.exists else {}
            return recent.get(key)
        return await asyncio.to_thread(_op)

    async def record_link(self, key, user_id, name):
        def _op():
            snap = self._recent.get()
            recent = (snap.to_dict() or {}) if snap.exists else {}
            recent[key] = {'u': user_id, 'n': name, 't': time.time()}
            recent = _prune_recent(recent)
            self._recent.set(recent)
        await asyncio.to_thread(_op)

    async def get_cached(self, key):
        def _op():
            snap = self._cache.get()
            cache = (snap.to_dict() or {}) if snap.exists else {}
            return cache.get(key)
        return await asyncio.to_thread(_op)

    async def set_cached(self, key, payload):
        def _op():
            snap = self._cache.get()
            cache = (snap.to_dict() or {}) if snap.exists else {}
            p = dict(payload); p['t'] = time.time()
            cache[key] = p
            cache = _prune(cache, CACHE_MAX, CACHE_TTL)
            self._cache.set(cache)
        await asyncio.to_thread(_op)

    async def record_chat(self, chat_id, title):
        def _op():
            data = self._read()
            data.setdefault('chats', {})
            c = data['chats'].setdefault(str(chat_id), {'count': 0})
            c['title'] = title or c.get('title', '')
            c['count'] = int(c.get('count', 0)) + 1
            c['last'] = time.time()
            self._doc.set({'chats': data['chats']}, merge=True)
        await asyncio.to_thread(_op)

    async def get_chats(self):
        data = await asyncio.to_thread(self._read)
        chats = data.get('chats', {}) or {}
        out = [{'id': k, **v} for k, v in chats.items()]
        out.sort(key=lambda x: x.get('count', 0), reverse=True)
        return out


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
            store = FirestoreRankingStore(client)
            # Health-check: una lettura di prova. Se Firestore non e' abilitato nel
            # progetto, qui esce un 403 ESPLICITO (invece di fallire in silenzio dopo).
            try:
                client.collection('bot_state').document('_healthcheck').get()
                logger.info("Ranking: Firestore raggiungibile (health-check OK)")
            except Exception as he:
                logger.error(
                    "Ranking: FIRESTORE NON RAGGIUNGIBILE — i dati NON verranno salvati! "
                    "Abilita 'Firestore Database' nella console Firebase del progetto. "
                    f"Dettaglio: {str(he)[:200]}"
                )
            return store
        except Exception as e:
            logger.error(f"Ranking: Firestore non utilizzabile, fallback JSON: {e}")
    return JsonRankingStore(json_fallback_path)
