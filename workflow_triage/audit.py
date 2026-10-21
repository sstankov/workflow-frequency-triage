"""Append-only public audit records and credential redaction."""
import fcntl
import re
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(text):
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9_.-]{12,}', r'\1[REDACTED]', text)


def log(logfile, speaker, kind, text):
    logfile.parent.mkdir(parents=True,exist_ok=True)
    cleaned = redact(text)
    with logfile.open('a',encoding='utf-8') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        f.write('\n## %s — %s — %s\n\n%s\n' % (now(),speaker,kind,cleaned))
        if cleaned != text:
            f.write('\nCredential-shaped text was redacted.\n')
