#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Переносить ../черга.json у хмарний репозиторій: медіа → m/<slug>/, адреси GitHub Pages → queue.json.

    python3 sync.py        (спершу git pull: стан опублікованих береться з хмари й не перезаписується)

Шляхи латиницею: Instagram має отримати адресу без кирилиці.
"""
import os, json, shutil, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'черга.json')
OUT = os.path.join(HERE, 'queue.json')
PAGES = 'https://kt-stal.github.io/ktstal-social/'
TR = dict(zip('абвгґдеєжзиіїйклмнопрстуфхцчшщьюя', ['a','b','v','h','g','d','e','ie','zh','z','y','i','i','i','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','iu','ia']))


def slug(s): return ''.join(TR.get(c, c) for c in s.lower()).replace("'", '')


def main():
    src = json.load(open(SRC, encoding='utf-8'))
    old = {x['id']: x for x in json.load(open(OUT, encoding='utf-8'))} if os.path.exists(OUT) else {}
    out, keep = [], set()
    for x in src:
        o = old.get(x['id'])
        if o and o.get('стан') in ('done', 'error'):
            out.append(o); continue
        sl = slug(x['id']); d = os.path.join(HERE, 'm', sl); os.makedirs(d, exist_ok=True); keep.add(sl)
        urls = []
        for f in x['файли']:
            p = os.path.normpath(os.path.join(os.path.dirname(SRC), f)); name = os.path.basename(p)
            ext = os.path.splitext(name)[1].lower(); dst = os.path.join(d, ('reel' if ext == '.mp4' else os.path.splitext(name)[0]) + ext)
            shutil.copyfile(p, dst)
            v = hashlib.sha1(open(dst, 'rb').read()).hexdigest()[:8]   # нова версія файлу = нова адреса (Meta кешує невдалі завантаження)
            urls.append(f'{PAGES}m/{sl}/{os.path.basename(dst)}?v={v}')
        y = {'id': x['id'], 'тип': x['тип'], 'час': x['час'], 'підпис': x['підпис'], 'urls': urls, 'стан': 'pending'}
        if x.get('обкладинка'):   # без неї Instagram бере перший кадр ролика
            cp = os.path.normpath(os.path.join(os.path.dirname(SRC), x['обкладинка'])); dst = os.path.join(d, 'cover.jpg'); shutil.copyfile(cp, dst)
            y['обкладинка_url'] = f"{PAGES}m/{sl}/cover.jpg?v={hashlib.sha1(open(dst, 'rb').read()).hexdigest()[:8]}"
        if o and o.get('помилки'): y['помилки'] = o['помилки']
        out.append(y)
    for sl in os.listdir(os.path.join(HERE, 'm')):
        if sl != 'stories' and sl not in keep and not any(slug(x['id']) == sl for x in out): shutil.rmtree(os.path.join(HERE, 'm', sl))
    out.sort(key=lambda x: x['час'])
    with open(OUT, 'w', encoding='utf-8') as f: json.dump(out, f, ensure_ascii=False, indent=1); f.write('\n')
    print(len(out), 'позицій →', OUT)


if __name__ == '__main__':
    main()
