"""Optional, bounded local diarization. Speaker IDs live only within one note."""
import asyncio
from collections import Counter
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import time

log = logging.getLogger(__name__)
MODEL_DIR = Path(os.getenv('VOICE_SPEAKER_MODELS', '/opt/voice-speakers'))
_busy = False


def memory_available():
    try:
        root = Path('/sys/fs/cgroup')
        limit = int((root / 'memory.max').read_text())
        current = int((root / 'memory.current').read_text())
        stats = dict(line.split() for line in (root / 'memory.stat').read_text().splitlines())
        return limit - current + int(stats.get('inactive_file', 0))
    except (OSError, ValueError):
        return 1024 * 1024 * 1024


async def diarize(audio, timeout=20):
    global _busy
    if (_busy or os.getenv('VOICE_SPEAKERS', '1') != '1' or memory_available() < 100 * 1024**2
            or not (MODEL_DIR / 'speaker.onnx').is_file() or not (MODEL_DIR / 'segmentation.onnx').is_file()):
        return []
    _busy = True
    proc = None
    output = Path(audio).with_name('speakers.json')
    started = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).resolve()), str(audio), str(output),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
        while proc.returncode is None:
            if time.monotonic() - started > timeout or memory_available() < 40 * 1024**2:
                log.info('Voice speaker analysis skipped: resource budget')
                return []
            await asyncio.sleep(.1)
        if proc.returncode != 0 or not output.exists() or output.stat().st_size > 100000:
            return []
        result = json.loads(output.read_text(encoding='utf-8'))
        log.info('Voice speaker analysis finished: seconds=%.1f clusters=%s',
                 time.monotonic() - started, len({item[2] for item in result}))
        return result
    except (OSError, ValueError, TypeError):
        return []
    finally:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        output.unlink(missing_ok=True)
        _busy = False


def label_text(text, words, segments):
    """Align acoustic turns to exact ASR words; never infer voices from content."""
    try:
        if not isinstance(words, list) or not words or len(words) > 3000 or not segments:
            return text
        valid = []
        durations = Counter()
        for start, end, speaker in segments:
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= 181
                    and isinstance(speaker, int) and speaker >= 0):
                return text
            durations[speaker] += end - start
            valid.append((start, end, speaker))
        known = {speaker for speaker, duration in durations.items() if duration >= 1}
        if len(known) < 2 or len(known) > 8:
            return text
        tokens, owners = [], []
        for word in words:
            start, end = float(word['start']), float(word['end'])
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= 181):
                return text
            matches = Counter()
            for a, b, speaker in valid:
                matches[speaker] += max(0, min(end, b) - max(start, a))
            ranked = matches.most_common()
            owner = None
            if ranked and end > start:
                speaker, overlap = ranked[0]
                runner_up = ranked[1][1] if len(ranked) > 1 else 0
                if speaker in known and overlap >= .65 * (end-start) and runner_up <= .2 * (end-start):
                    owner = speaker
            pieces = re.findall(r'\w+', word['word'].casefold())
            tokens.extend(pieces)
            owners.extend([owner] * len(pieces))
        spans = list(re.finditer(r'\w+', text))
        if tokens != [match.group().casefold() for match in spans]:
            return text
        counts = Counter(owner for owner in owners if owner is not None)
        if len([owner for owner, count in counts.items() if count >= 3]) < 2:
            return text
        # If most words cannot be assigned, labels would misrepresent the note.
        if owners.count(None) > len(owners) * .25:
            return text
        numbers, turns = {}, []
        first = 0
        for index in range(1, len(owners) + 1):
            if index < len(owners) and owners[index] == owners[first]:
                continue
            owner = owners[first]
            if owner is None:
                label = 'Voce non distinta'
            else:
                numbers.setdefault(owner, len(numbers) + 1)
                label = f'Voce {numbers[owner]}'
            a = 0 if first == 0 else spans[first].start()
            b = spans[index].start() if index < len(spans) else len(text)
            turns.append(label + ':\n' + text[a:b].strip())
            first = index
        return '\n\n'.join(turns)
    except (ValueError, TypeError, KeyError, AttributeError):
        return text


def worker(audio, output):
    # Import model runtime only in a child; freeing its memory is deterministic.
    import wave
    import numpy as np
    import sherpa_onnx as sherpa
    with wave.open(audio, 'rb') as source:
        if source.getframerate() != 16000 or source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError('expected mono PCM16')
        if source.getnframes() > 180 * 16000:
            raise ValueError('duration limit')
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768
    config = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(MODEL_DIR / 'segmentation.onnx'), window_shift_ratio=.5), num_threads=1),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(MODEL_DIR / 'speaker.onnx'), num_threads=1),
        clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=.6),
        min_duration_on=.3, min_duration_off=.5)
    diarizer = sherpa.OfflineSpeakerDiarization(config)
    result = diarizer.process(samples).sort_by_start_time()
    Path(output).write_text(json.dumps([[round(s.start, 3), round(s.end, 3), s.speaker] for s in result]), encoding='utf-8')


if __name__ == '__main__':
    worker(sys.argv[1], sys.argv[2])
