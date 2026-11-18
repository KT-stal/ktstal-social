#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автопостинг КТ-Сталь в Instagram з GitHub Actions (Mac не потрібен).

    python3 bot/post_ig.py --status          черга і що вийде наступним
    python3 bot/post_ig.py --whoami          перевірити токен (нічого не публікує)
    python3 bot/post_ig.py --check <id>      створити контейнер без публікації
    python3 bot/post_ig.py --publish <id>    опублікувати одну позицію зараз
    python3 bot/post_ig.py --run             опублікувати позицію, якій настав час (cron)

Токен і id акаунта — лише зі змінних IG_TOKEN, IG_USER_ID (секрети репозиторію).
Запобіжники: не більше одного допису на київську добу; перед публікацією звіряємо
останні дописи акаунта, щоб збій після media_publish не дав дубля; стан пишемо в
queue.json одразу після публікації, workflow комітить його назад.
"""
import sys, os, json, time, datetime, urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo

KYIV = ZoneInfo('Europe/Kyiv')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, 'queue.json')
BASE = 'https://graph.facebook.com/v23.0'   # ключ «Instagram API (єдиний вхід)» працює через граф Facebook з id акаунта
WAIT_S = 600


def log(msg):
    print(datetime.datetime.now(KYIV).strftime('%Y-%m-%d %H:%M:%S'), msg, flush=True)


def env():
    tok, uid = os.environ.get('IG_TOKEN', '').strip(), os.environ.get('IG_USER_ID', '').strip()
    if not tok or not uid: raise SystemExit('немає IG_TOKEN або IG_USER_ID')
    return tok, uid


def api(path, data=None, method=None, params=None):
    tok, _ = env()
    url = path if path.startswith('http') else f'{BASE}/{path.lstrip("/")}'
    if params: url += '?' + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method or ('POST' if body else 'GET'),
                                 headers={'Authorization': f'Bearer {tok}'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{e.code} {e.read().decode()[:400]}') from None


def load():
    return json.load(open(QUEUE, encoding='utf-8'))


def save(items):
    with open(QUEUE, 'w', encoding='utf-8') as f: json.dump(items, f, ensure_ascii=False, indent=1); f.write('\n')


def when(x): return datetime.datetime.fromisoformat(x['час'])


def published_on(items, day):
    return [x for x in items if x.get('стан') == 'done' and x.get('опубліковано') and
            datetime.datetime.fromisoformat(x['опубліковано']).astimezone(KYIV).date() == day]


def due(items, now):
    """Найстаріша неопублікована позиція, якій настав час; None, якщо сьогодні вже був допис."""
    if published_on(items, now.astimezone(KYIV).date()): return None
    ready = [x for x in items if x.get('стан', 'pending') == 'pending' and when(x) <= now]
    return min(ready, key=when) if ready else None


def wait_ready(cid):
    t0 = time.time()
    while time.time() - t0 < WAIT_S:
        st = api(cid, params={'fields': 'status_code,status'})
        if st.get('status_code') == 'FINISHED': return
        if st.get('status_code') in ('ERROR', 'EXPIRED'): raise RuntimeError(f'контейнер {cid}: {st}')
        time.sleep(8)
    raise RuntimeError(f'контейнер {cid} не готовий за {WAIT_S} с')


def container(x):
    _, me = env()
    if x['тип'] == 'reel':
        cid = api(f'{me}/media', {'media_type': 'REELS', 'video_url': x['urls'][0], 'caption': x['підпис'],
                                  'share_to_feed': 'true', **({'cover_url': x['обкладинка_url']} if x.get('обкладинка_url') else {})})['id']
    elif x['тип'] == 'carousel':
        kids = [api(f'{me}/media', {'image_url': u, 'is_carousel_item': 'true'})['id'] for u in x['urls']]
        for k in kids: wait_ready(k)
        cid = api(f'{me}/media', {'media_type': 'CAROUSEL', 'children': ','.join(kids), 'caption': x['підпис']})['id']
    else:
        cid = api(f'{me}/media', {'image_url': x['urls'][0], 'caption': x['підпис']})['id']
    wait_ready(cid)
    return cid


def already_live(x):
    """Чи вже є на акаунті допис із цим підписом (захист від дубля після збою)."""
    head = x['підпис'][:80]
    for m in api(f'{env()[1]}/media', params={'fields': 'id,caption,permalink,timestamp', 'limit': 25}).get('data', []):
        if (m.get('caption') or '')[:80] == head: return m
    return None


def publish(items, x):
    live = already_live(x)
    if live:
        log(f'{x["id"]}: вже опубліковано раніше {live.get("permalink")} — лише позначаю')
        x.update(стан='done', media_id=live['id'], посилання=live.get('permalink'), опубліковано=live.get('timestamp') or datetime.datetime.now(KYIV).isoformat())
        save(items); return x
    cid = container(x)
    _, uid = env()
    mid = api(f'{uid}/media_publish', {'creation_id': cid})['id']
    x.update(стан='done', media_id=mid, опубліковано=datetime.datetime.now(KYIV).isoformat()); save(items)
    try: x['посилання'] = api(mid, params={'fields': 'permalink'}).get('permalink'); save(items)
    except Exception as e: log(f'посилання не отримано: {e}')
    log(f'{x["id"]}: опубліковано {x.get("посилання") or mid}')
    return x


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    items = load(); now = datetime.datetime.now(KYIV)
    by = {x['id']: x for x in items}
    if not a or a[0] == '--status':
        for x in sorted(items, key=when): print(x['час'][:16], x.get('стан', 'pending').ljust(8), x['тип'].ljust(8), x['id'], x.get('посилання', ''))
        nx = due(items, now); print('наступне зараз:', nx['id'] if nx else '—'); return
    if a[0] == '--whoami':
        print(json.dumps(api(env()[1], params={'fields': 'id,username,media_count,followers_count'}), ensure_ascii=False))
        print(json.dumps(api(f'{env()[1]}/content_publishing_limit', params={'fields': 'quota_usage,config'}), ensure_ascii=False)); return
    if a[0] == '--check':
        cid = container(by[a[1]]); print('контейнер готовий, не опубліковано:', cid); return
    if os.environ.get('ENABLED', '1') != '1': log('вимкнено (ENABLED != 1)'); return
    if a[0] == '--publish': publish(items, by[a[1]]); return
    if a[0] == '--run':
        x = due(items, now)
        if not x: log('нічого публікувати'); return
        try: publish(items, x)
        except Exception as e:
            x['помилки'] = x.get('помилки', 0) + 1; x['остання_помилка'] = str(e)[:300]
            if x['помилки'] >= 3: x['стан'] = 'error'
            save(items); raise
        return
    raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
