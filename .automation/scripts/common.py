from __future__ import annotations
import json, os, re, shutil, subprocess, time
from datetime import datetime
from pathlib import Path

MIN_CODEX=(0,153,0)
USAGE_PATTERNS=["you've hit your usage limit","you have hit your usage limit","usage limit","try again at","quota exceeded","rate limit exceeded","rate_limit_exceeded"]
AUTH_PATTERNS=["not logged in","authentication","unauthorized","forbidden","invalid api key"]
TRANSIENT_PATTERNS=["timed out","timeout","connection reset","temporarily unavailable","at capacity","502","503","504"]

def repo_root():
    candidate=Path(__file__).resolve().parents[2]
    try:
        out=subprocess.check_output(['git','-C',str(candidate),'rev-parse','--show-toplevel'],text=True,encoding='utf-8',errors='replace',stderr=subprocess.DEVNULL).strip(); return Path(out).resolve()
    except Exception:return candidate.resolve()

def load_toml(path):
    import tomllib
    with Path(path).open('rb') as f:return tomllib.load(f)

def load_json(path,default=None):
    p=Path(path)
    if not p.exists():return default
    with p.open(encoding='utf-8') as f:return json.load(f)

def save_json(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); tmp.replace(p)

def resolve_executable(binary='codex'):
    value=str(binary)
    p=Path(value).expanduser()
    if p.is_absolute() or '/' in value or '\\' in value:
        return str(p)
    resolved=shutil.which(value)
    if resolved:
        return resolved
    if os.name=='nt':
        for candidate in (value+'.cmd', value+'.exe', value+'.bat'):
            resolved=shutil.which(candidate)
            if resolved:
                return resolved
    return value

def codex_version(binary='codex'):
    exe=resolve_executable(binary)
    try:out=subprocess.check_output([exe,'--version'],text=True,encoding='utf-8',errors='replace',stderr=subprocess.STDOUT,timeout=20)
    except Exception:return None,''
    m=re.search(r'(\d+)\.(\d+)\.(\d+)',out); return (tuple(map(int,m.groups())) if m else None),out.strip()

def classify_output(text,returncode):
    low=text.lower()
    if any(p in low for p in USAGE_PATTERNS):return 'allowance'
    if any(p in low for p in AUTH_PATTERNS):return 'auth'
    if any(p in low for p in TRANSIENT_PATTERNS):return 'transient'
    return 'success' if returncode==0 else 'fatal'

def parse_reset_epoch(text):
    """Best-effort parser for common Codex allowance reset messages.

    If no trustworthy reset can be parsed the supervisor falls back to conservative probing,
    so this function intentionally returns None rather than guessing.
    """
    now=datetime.now().astimezone()
    # ISO 8601 timestamp after "try again at".
    m=re.search(r'try again at\s+(\d{4}-\d{2}-\d{2}[T ][0-9:]+(?:Z|[+-]\d{2}:?\d{2})?)',text,re.I)
    if m:
        raw=m.group(1).replace(' ','T',1)
        try:
            if raw.endswith('Z'): raw=raw[:-1]+'+00:00'
            return datetime.fromisoformat(raw).timestamp()
        except ValueError: pass
    # Month/day with optional year, e.g. Sep 15, 2026 3:45 PM or Sep 15 3:45 PM.
    m=re.search(r'try again at\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\s+\d{1,2}:\d{2}\s*(?:AM|PM))',text,re.I)
    if m:
        raw=re.sub(r'(\d+)(st|nd|rd|th)',r'\1',m.group(1),flags=re.I).replace(',','').strip()
        if re.search(r'\b\d{4}\b',raw):
            candidates=[(raw,'%b %d %Y %I:%M %p'),(raw,'%B %d %Y %I:%M %p')]
        else:
            raw_with_year=f'{raw} {now.year}'
            candidates=[(raw_with_year,'%b %d %I:%M %p %Y'),(raw_with_year,'%B %d %I:%M %p %Y')]
        for value,fmt in candidates:
            try:
                dt=datetime.strptime(value,fmt)
                aware=dt.replace(tzinfo=now.tzinfo)
                if not re.search(r'\b\d{4}\b',raw) and aware.timestamp() < now.timestamp()-86400:
                    aware=aware.replace(year=now.year+1)
                return aware.timestamp()
            except ValueError: pass
    # Time only, trusted only for the next 24h local window.
    m=re.search(r'try again at\s+(\d{1,2}:\d{2}\s*(?:AM|PM))',text,re.I)
    if m:
        try:
            t=datetime.strptime(m.group(1).upper(),'%I:%M %p').time()
            dt=now.replace(hour=t.hour,minute=t.minute,second=0,microsecond=0)
            if dt.timestamp() <= now.timestamp():
                from datetime import timedelta
                dt=dt+timedelta(days=1)
            return dt.timestamp()
        except ValueError: pass
    return None

def extract_thread_id(jsonl):
    for line in jsonl.splitlines():
        try:o=json.loads(line)
        except Exception:continue
        if o.get('type')=='thread.started' and o.get('thread_id'):return o['thread_id']
    return None

def git(args,root,check=True):return subprocess.run(['git','-C',str(root),*args],text=True,encoding='utf-8',errors='replace',capture_output=True,check=check)

def kill_process_tree(proc):
    if proc.poll() is not None:return
    if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        import signal
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:return
        time.sleep(3)
        if proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
