"""External reviewer adapter; orchestration depends on the callable contract."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from .audit import log, redact
from .review import review_schema
from .serialization import write_json


class Reviewer(Protocol):
    def __call__(self, prompt: str, logfile: Path, timeout: int = 600) -> tuple[dict, dict]:
        """Return the structured review and usage; raise on review failure."""
        ...


def call_agent(prompt,logfile,timeout=600):
    binary = shutil.which('codex')
    if not binary:
        raise RuntimeError('Codex CLI is not installed. Install and sign in with codex login, then rerun.')
    log(logfile,'pipeline','agent prompt',prompt)
    # The agent receives all evidence on stdin and has no reason to access the repo.
    # Only public agent messages are retained; reasoning events are never logged.
    with tempfile.TemporaryDirectory(prefix='workflow-review-') as folder:
        folder = Path(folder)
        schema,answer = folder/'schema.json',folder/'answer.json'
        write_json(schema,review_schema())
        command = [binary,'exec','--sandbox','read-only','--skip-git-repo-check','--ephemeral','--json','--color','never','--cd',str(folder),'--output-schema',str(schema),'--output-last-message',str(answer),'-']
        process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            stdout,stderr = process.communicate(prompt,timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid,signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.communicate()
            raise RuntimeError('Agent review timed out; rerun with a larger --timeout.')
        usage = {}
        errors = []
        for line in stdout.splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            item = event.get('item',{})
            if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                log(logfile,'step2-agent','public response',item.get('text',''))
            if event.get('type') == 'turn.completed': usage = event.get('usage',{})
            if event.get('type') in {'error','turn.failed'}:
                errors.append(redact(str(event.get('message') or event.get('error') or 'Agent failed')))
        if process.returncode or not answer.exists():
            raise RuntimeError('Codex review failed (exit %s). %s' % (process.returncode,'; '.join(errors) or 'Check codex login status and CLI configuration.'))
        raw = answer.read_text()
        log(logfile,'step2-agent','final structured response',raw)
        return json.loads(raw),usage
