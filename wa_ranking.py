"""Per-group weekly rankings and durable delivery snapshots."""
from datetime import datetime, timedelta, timezone
import hashlib


def current_period(now=None):
    now = now or datetime.now(timezone.utc)
    boundary = (now - timedelta(days=(now.weekday() - 5) % 7)).replace(
        hour=20, minute=0, second=0, microsecond=0)
    if now < boundary:
        boundary -= timedelta(days=7)
    return boundary.isoformat()


def render_board(board, quote):
    lines = ['\U0001f973 *RANKING SETTIMANALE* \U0001f973', '']
    for index, badge in enumerate(('\U0001f947', '\U0001f948', '\U0001f949')):
        if index < len(board):
            _, count, name = board[index]
            name = str(name).replace('\n', ' ').replace('*', '').replace('_', '')
            lines.append(f'{badge} {name} \u2014 *{count}* video')
        else:
            lines.append(f'{badge} \u2014 *0* video')
    if quote:
        lines.extend(['', '\U0001f4dc _' + quote.replace('_', '') + '_'])
    return '\n'.join(lines)


def update_group(data, jid, period, quote, point=None, ack=None):
    from ranking_store import _apply_point, _build_board
    previous = data.setdefault('period', period)
    pending = data.setdefault('pending', {})
    if previous != period:
        board = _build_board(data, 'weekly', 3)
        if board:
            ident = hashlib.sha256(f'{jid}:{previous}'.encode()).hexdigest()[:24].upper()
            pending[ident] = {'id': ident, 'jid': jid, 'text': render_board(board, quote)}
        data['weekly'] = {}
        data['period'] = period
    if point:
        _apply_point(data, point[0], point[1])
    if ack:
        pending.pop(ack, None)
    return list(pending.values())
