# Render ပေါ်မှာ Full App (Whisper ပါ) Deploy လုပ်နည်း

ဒီဖိုင်တွေက **အဆင်သင့်** ဖြစ်နေပြီ —

| ဖိုင် | လုပ်ဆောင်ချက် |
|---|---|
| `render.yaml` | Render Blueprint — service, disk, env vars အကုန်ပါ |
| `wsgi.py` | Gunicorn entry point + `/api/ready` health check + background model load |
| `Procfile` | `gunicorn -w 1 --threads 4 --timeout 180` |
| `requirements.txt` | flask, gunicorn, faster-whisper, av, numpy |

---

## နည်း A — Render Dashboard (အလွယ်ဆုံး၊ ၁၀ မိနစ်)

### ၁။ Code ကို GitHub ပေါ် တင်ပါ

```bash
cd mmpolite
git init
git add .
git commit -m "Burmese polite phone-call helper"
git branch -M main
git remote add origin https://github.com/<သင့်-username>/mm-phone-helper.git
git push -u origin main
```

> GitHub account မရှိရင် [github.com](https://github.com) မှာ အခမဲ့ ဖွင့်ပါ။

### ၂။ Render မှာ Blueprint ဖန်တီးပါ

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**
2. GitHub repo `mm-phone-helper` ကို ရွေးပါ
3. Render က `render.yaml` ကို အလိုအလျောက် ဖတ်ပြီး service ဖန်တီးပေးမယ်
4. **Apply** နှိပ်ပါ

### ၃။ စောင့်ပါ (၃–၅ မိနစ်)

Build log ထဲမှာ ဒါတွေ တွေ့ရမယ် —

```
==> Building...
Collecting flask ... Collecting faster-whisper ...
==> Your service is live 🎉
```

ပြီးရင် **`https://mm-phone-helper.onrender.com`** ဆိုတဲ့ URL ရမယ်။
ဒါက **ဖုန်းမှာ ဖွင့်လို့ရတဲ့ အမြဲတမ်း HTTPS link** ပါ။ 🎉

---

## နည်း B — Render API (CLI နဲ့)

Render API key ([account settings](https://dashboard.render.com/account#api-keys)) ရှိရင် —

```bash
curl -X POST "https://api.render.com/v1/blueprints" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mm-phone-helper",
    "repository": {"url": "https://github.com/<username>/mm-phone-helper"},
    "branch": "main",
    "autoDeploy": true
  }'
```

---

## Deploy ပြီးရင် စစ်ရမည့်အရာ

```bash
BASE=https://mm-phone-helper.onrender.com

# 1. model ဖွင့်ပြီးသားလား
curl -s $BASE/api/ready
#    -> {"app":"ok","model":"tiny.en","model_loaded":true,...}

# 2. UI ပေါ်လား
curl -s -o /dev/null -w "%{http_code}\n" $BASE/
#    -> 200

# 3. phrasebook
curl -s "$BASE/api/phrasebook?gender=female" | head -c 200

# 4. အသံ → မြန်မာ
curl -s -X POST "$BASE/api/transcribe?gender=male" \
     -F "audio=@/path/to/call.wav"
```

---

## ကုန်ကျစရိတ်နှင့် ကန့်သတ်ချက်

| | Render **Free** | Render **Starter ($7/လ)** |
|---|---|---|
| RAM | 512 MB | 2 GB |
| Cold start | 15 မိနစ် မသုံးရင် အိပ်မယ်၊ နောက်တစ်ခါ ~30 စက္ကန့် စောင့်ရမယ် | မအိပ်ဘူး |
| Disk (model cache) | 1 GB ✅ | 1 GB ✅ |
| Concurrent | 1 ဖုန်းတစ်ချိန်တစ်ခါ လုံလောက် | ပိုများများ |

**⚠️ Free tier မှာ persistent disk မရပါ**

Render ရဲ့ တရားဝင် docs အတိုင်း — *"Free web services don't support:
Persistent disks"*၊ ပြီးတော့ filesystem က ephemeral ဖြစ်လို့ **၁၅ မိနစ်
အသုံးမပြုရင် service အိပ်ပြီး ရေးထားသမျှ အကုန်ပျောက်တယ်**။

ဒါကြောင့် model ကို runtime မှာ download လုပ်ရင် **cold start တိုင်းမှာ
75 MB ပြန် download** ရမယ် — ဖုန်းပြောနေတုန်း ၁–၂ မိနစ် စောင့်ရမယ်။ မသုံးနိုင်ဘူး။

**ဖြေရှင်းချက် — model ကို repo ထဲ ထည့်ပြီး commit လုပ်ပါ**

```bash
python3 fetch_model.py     # -> models/tiny.en/  (74 MB)
git add models && git commit -m "bundle whisper tiny.en"
```

74 MB က GitHub ရဲ့ **100 MB per-file limit အောက်** မှာ ရှိလို့ Git LFS မလိုဘူး။
တိုင်းတာချက် — bundled directory ကနေ load တာ **၀.၄ စက္ကန့်** (download လုပ်တာထက်
များစွာ မြန်တယ်)။ Free tier ရဲ့ cold start က Render ရဲ့ ~၆၀ စက္ကန့် spin-up ပဲ ကျန်တော့တယ်။

**Paid (Starter $7/လ) သုံးရင်** — `render-paid.yaml` ကို သုံးပါ။ persistent disk
ပါတာမို့ repo သေးသေးနဲ့ cold start မြန်တယ်။

**အခြား ချိန်ညှိချက်များ**

- `MAX_AUDIO_MB=12` — 512 MB RAM မှာ decode မပေါက်ကွဲအောင်
- `healthCheckPath=/api/ready` — model မဖွင့်ခင်မှာလည်း ချက်ချင်း ဖြေလို့
  Render က deploy ကို မသတ်ဘူး
- `-w 1 --threads 4` — worker တစ်ခုတည်း (Whisper ~200 MB RAM ယူလို့
  512 MB မှာ ၂ ခုဆို OOM ဖြစ်မယ်)။ Concurrency က thread တွေကနေ ရတယ်။

---

## အသံသွင်းခြင်း ရ/မရ

**Render က HTTPS ပေးလို့ မိုက်ခရိုဖုန်း ရပါတယ်။** ✅

ဒါက sandbox preview နဲ့ အဓိက ကွာခြားချက် —

| | Sandbox preview | Render |
|---|---|---|
| URL | token လိုတယ်၊ copy မရ | `https://…onrender.com` တိုက်ရိုက်ဖွင့်လို့ရ |
| မိုက်ခရိုဖုန်း | ✅ (HTTPS) | ✅ (HTTPS) |
| ဖုန်းမှာ ဖွင့်လို့ | ❌ | ✅ |
| အမြဲတမ်း | ❌ (conversation ပိတ်ရင် ရပ်) | ✅ |

---

## ပြဿနာ ဖြေရှင်း

**Build fail ဖြစ်တယ်**
→ Log ထဲမှာ `av` wheel build error တွေ့ရင် `requirements.txt` ထဲမှာ
`av>=13` ကို `av==15.1.0` လို့ pin လုပ်ပါ (cp311 wheel အသေအချာ ရှိတယ်)။

**`/api/ready` မှာ `model_loaded: false` ဖြစ်နေတယ်**
→ `models/tiny.en` ကို commit မလုပ်ထားလို့ ဖြစ်နိုင်တယ်။ အောက်ပါအတိုင်း စစ်ပါ —

```bash
git ls-files models/ | head      # model.bin ပါရမယ်။ ဗလာဆို commit မလုပ်ထားဘူး
```

`fetch_model.py` ပြန် run ပြီး `git add models` လုပ်ပါ။ Paid plan သုံးရင်
service shell ထဲမှာ `python3 fetch_model.py` တစ်ခါ run ပါ။

**Transcribe လုပ်ရင် 500 ပြန်တယ်**
→ Render → Logs ကြည့်ပါ။ အများဆုံး အကြောင်းရင်းက RAM ကုန်တာ။
`MAX_AUDIO_MB` ကို `8` လျှော့ပါ။

**အသံသွင်းခလုတ် အလုပ်မလုပ်ဘူး**
→ browser က မိုက်ခွင့်ပြုချက် မေးမယ်။ **Allow** နှိပ်ပါ။
iOS Safari မှာ `getUserMedia` က HTTPS လိုတယ် — Render က ပေးပြီးသား။

---

## တခြား Host တွေ

`Procfile` ပါပြီးသားမို့ ဒါတွေမှာလည်း တိုက်ရိုက် အလုပ်လုပ်တယ် —

```bash
# Railway
railway up

# Fly.io  (fly.toml လိုတယ်)
fly launch
fly deploy

# VPS (Ubuntu)
sudo apt install python3.11-venv
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
gunicorn -w 1 --threads 4 -b 0.0.0.0:8000 wsgi:app
# nginx + certbot နဲ့ HTTPS တင်ပါ (မိုက်အတွက် HTTPS မဖြစ်မနေ လိုတယ်)
```
