"""一次性：在 GL 纯 CPU job 内逐对象流式读回 HF 私有 bucket，边下边算 sha256（不落盘），与 SHA256SUMS 比对。
用法：python verify.py <SHA256SUMS> [--limit N]；token 只取环境变量 HF_TOKEN。"""
import hashlib, json, os, ssl, sys, time, urllib.parse, urllib.request
import certifi
CTX = ssl.create_default_context(cafile=certifi.where())  # uv 解释器无系统 CA，改用 certifi
BUCKET = "HongzeFu/robomme-hard-v9-noise-baseline"
EP = "https://huggingface.co"
TOK = os.environ.get("HF_TOKEN")
if not TOK:
    print("HF_VERIFY=FAIL reason=no_token"); sys.exit(2)
H = {"Authorization": f"Bearer {TOK}"}
args = sys.argv[1:]
only = None
if "--only" in args:
    i = args.index("--only"); only = set(args[i + 1].split(",")); del args[i:i + 2]
limit = None
if "--limit" in args:
    i = args.index("--limit"); limit = int(args[i + 1]); del args[i:i + 2]
want = {}
for line in open(args[0]):
    sha, path = line.rstrip("\n").split("  ", 1)
    want[path] = sha
for extra in ("SHA256SUMS", "identities.jsonl", "manifest.json"):
    want.setdefault(extra, None)  # 清单文件本身只核存在与字节数

def get(url):
    req = urllib.request.Request(url, headers=H)
    for k in range(5):
        try:
            return urllib.request.urlopen(req, timeout=120, context=CTX)
        except Exception as e:  # 有限重试，只针对网络故障
            print(f"RETRY {k} {url[:120]} {type(e).__name__}: {e}", flush=True); time.sleep(5 * (k + 1))
    raise RuntimeError(f"读取失败 {url}")

# 列出全部对象（分页靠 Link: rel="next"）
remote = {}
url = f"{EP}/api/buckets/{BUCKET}/tree?recursive=true"
while url:
    r = get(url)
    for it in json.load(r):
        if it.get("type") == "file":
            remote[it["path"]] = int(it["size"])
    nxt = None
    for part in (r.headers.get("Link") or "").split(","):
        if 'rel="next"' in part:
            nxt = part[part.find("<") + 1:part.find(">")]
    url = nxt
print(f"LISTED objects={len(remote)} expected={len(want)}", flush=True)
missing = sorted(set(want) - set(remote)); extra = sorted(set(remote) - set(want))
todo = sorted(p for p in want if p in remote and want[p] is not None)
if only is not None:
    todo = sorted(p for p in todo if p in only)
if limit is not None:
    todo = sorted(todo, key=lambda p: remote[p])[:limit]
sha_ok = size_ok = 0; bad = []
t0 = time.time(); nbytes = 0
for n, p in enumerate(todo, 1):
    r = get(f"{EP}/buckets/{BUCKET}/resolve/{urllib.parse.quote(p, safe='')}")
    h = hashlib.sha256(); got = 0
    while True:
        b = r.read(8 << 20)
        if not b: break
        h.update(b); got += len(b)
    nbytes += got
    if got == remote[p]: size_ok += 1
    if h.hexdigest() == want[p]: sha_ok += 1
    else: bad.append(p); print(f"MISMATCH {p} got={h.hexdigest()} want={want[p]}", flush=True)
    if n % 50 == 0 or n == len(todo):
        print(f"PROGRESS {n}/{len(todo)} {nbytes/1e9:.1f}GB {nbytes/1e6/max(time.time()-t0,1):.0f}MB/s", flush=True)
for p in missing[:20]: print("MISSING", p)
for p in extra[:20]: print("EXTRA", p)
full = limit is None and only is None
ok = not bad and size_ok == len(todo) and sha_ok == len(todo) and (not full or (not missing and not extra))
print(f"HF_VERIFY={'PASS' if ok else 'FAIL'} objects={len(remote)} checked={len(todo)} sha_match={sha_ok} size_equal={size_ok} missing={len(missing)} extra={len(extra)}" + ("" if full else f" partial_only={len(only) if only else 0} smoke_limit={limit}"))
