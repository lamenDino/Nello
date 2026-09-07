"""Prepare downloaded videos for WhatsApp, independently of their source codec."""

import os
import subprocess
import tempfile


def prepare_video(path, timeout=180):
    """Return a new H.264/AAC MP4; leave the source intact on failure.

    A .mp4 extension alone does not guarantee compatible codecs. Decode the
    entire source so corrupt downloads fail before they reach WhatsApp.
    """
    fd, output = tempfile.mkstemp(prefix='wa_', suffix='.mp4',
                                  dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    try:
        subprocess.run([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-xerror', '-y', '-threads', '1', '-i', os.path.abspath(path),
            '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1',
            '-vf', "scale=w='min(1280,iw)':h='min(1280,ih)':"
                   'force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1',
            '-r', '30', '-c:v', 'libx264', '-threads', '1',
            '-preset', 'veryfast', '-crf', '23', '-profile:v', 'baseline',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ac', '2', '-ar', '48000',
            '-b:a', '128k', '-movflags', '+faststart', output,
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=timeout)
        if os.path.getsize(output) == 0:
            raise ValueError('empty converted video')
        return output
    except BaseException:
        os.remove(output)
        raise
