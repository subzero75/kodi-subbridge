"""SubBridge: Kodi subtitle add-on that asks Stremio subtitle add-ons.

Kodi calls it with ?action=search (the playing video), ?action=manualsearch&searchstring=...
and ?action=download&data=... for the result the viewer picked."""
import difflib
import io
import json
import os
import re
import sys
import time
import zipfile
from urllib.parse import parse_qs, quote, unquote, urlparse

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import langs, stremio, util, video

CACHE_MINUTES = 30
SUB_EXTS = ('srt', 'ass', 'ssa', 'vtt', 'sub', 'smi', 'txt')
LOCAL_SERVER = re.compile(r'^https?://(?:127\.0\.0\.1|localhost):11470/')
HEARING = re.compile(r'(?i)(?:^|[^a-z])(?:sdh|hi|cc|hearing[ ._-]?impaired)(?:[^a-z]|$)')


def params():
    p = parse_qs(sys.argv[2].lstrip('?')) if len(sys.argv) > 2 else {}
    return {k: v[0] for k, v in p.items()}


def wanted_languages(p):
    names = [n for n in (p.get('languages') or '').split(',') if n.strip()]
    if not names:
        names = util.rpc('Settings.GetSettingValue', {'setting': 'subtitles.languages'}).get('value') or []
    codes = langs.wanted(names)
    pref = langs.code(p.get('preferredlanguage') or '')[0]
    if pref:
        codes = [pref] + [c for c in codes if c != pref]
    return codes or ['eng']


VIDEO_EXT = re.compile(r'(?i)\.(?:mkv|mp4|avi|ts|m2ts|mov|webm|wmv|m4v|mpg|srt|ass|ssa|vtt|sub)$')


def _flat(text):
    return re.sub(r'[^a-z0-9]+', ' ', VIDEO_EXT.sub('', text or '').lower()).strip()


def collect(info, extra, timeout):
    """[(base, name, subs)] for the first IMDb id that gets any answer."""
    ids = list(info['ids'])
    looked_up = False
    cache = util.Store('searches.json', CACHE_MINUTES * 60)
    tried = set()
    while True:
        if not ids and info.get('lookup') and not looked_up:
            looked_up = True
            title, year = info['lookup']
            found = video.imdb_from_title(title, year, movie=info['kind'] == 'movie')
            if found:
                ids.append(found)
        if not ids:
            return []
        imdb = ids.pop(0)
        if imdb in tried:
            continue
        tried.add(imdb)
        vid = video.stremio_id(info, imdb)
        key = json.dumps([info['kind'], vid, extra, stremio.links()])
        answer = cache.get(key)
        if answer is None:
            answer = stremio.search(info['kind'], vid, extra, timeout)
            if any(subs for _, _, subs in answer):
                cache.put(key, answer)
                cache.save()
        else:
            util.log('%s %s: from the last %d minutes' % (info['kind'], vid, CACHE_MINUTES))
        if any(subs for _, _, subs in answer):
            return answer


def results(answer, wanted, all_languages, filename):
    """List entries, best first: the preferred language, then file-name matches."""
    out = []
    seen = set()
    count = {}
    for order, (base, source, subs) in enumerate(answer):
        for n, s in enumerate(subs):
            raw_lang = str(s.get('lang') or '').strip()
            label = str(s.get('label') or '').strip()
            c, variant = langs.code(raw_lang)
            note = ''
            if not c:
                # free text such as SubMaker's 'Make Arabic' (an AI translation made on download)
                if raw_lang[:1] in ('!', '⚠'):
                    continue  # the add-on's own error or notice
                c = langs.in_text(raw_lang + ' ' + label, wanted)
                if not c:
                    continue
                note = raw_lang
            if not all_languages and c not in wanted:
                continue
            url = s['url']
            if LOCAL_SERVER.match(url):
                q = parse_qs(urlparse(url).query)
                if 'from' not in q:
                    continue  # a file inside a torrent on Stremio's own streaming server
                url = q['from'][0]
            if url in seen:
                continue
            seen.add(url)
            release = label if label and label.lower() != raw_lang.lower() else ''
            if not release:
                tail = unquote(urlparse(url).path.rsplit('/', 1)[-1])
                release = os.path.splitext(tail)[0] if re.search(r'[a-z].*[._ ].*[a-z]', tail, re.I) and len(tail) > 12 else ''
            if note and note.lower() not in release.lower():
                release = '%s - %s' % (note, release) if release else note
            count[(source, c)] = count.get((source, c), 0) + 1
            shown = '%s: %s' % (source, release or '%s #%d' % (langs.name(c, variant), count[(source, c)]))
            match = 0.0
            if filename and release:
                match = difflib.SequenceMatcher(None, _flat(release), _flat(filename)).ratio()
            out.append({
                'lang': c, 'variant': variant, 'label2': shown, 'release': release or shown,
                'url': url, 'source': source, 'sync': match >= 0.9,
                'hi': bool(HEARING.search(label)) if label else False,
                # AI translations made on download come after real subtitles of that language
                'rank': (wanted.index(c) if c in wanted else len(wanted), 1 if note else 0,
                         0 if match >= 0.9 else 1, -round(match, 1), order, n),
            })
    out.sort(key=lambda r: r['rank'])
    return out


def do_search(handle, p, manual=False):
    wanted = wanted_languages(p)
    if manual:
        info = video.from_search_string(p.get('searchstring'))
        extra = {}
    else:
        info = video.playing()
        extra = video.file_details(info['path'], util.setting_bool('hash', True))
    timeout = max(3, util.setting_int('timeout', 10) or 10)
    util.log('search: %s, languages %s, file details %s' % (
        json.dumps({k: info.get(k) for k in ('kind', 'ids', 'title', 'year', 'season', 'episode')}),
        wanted, sorted(extra)))
    answer = collect(info, extra, timeout)
    found = results(answer, wanted, util.setting_bool('all_languages', False), extra.get('filename', ''))
    util.log('%d subtitles listed' % len(found))
    for r in found:
        li = xbmcgui.ListItem(label=langs.name(r['lang'], r['variant']), label2=r['label2'])
        li.setArt({'icon': '5' if r['sync'] else '0', 'thumb': langs.flag(r['lang'], r['variant'])})
        li.setProperty('sync', 'true' if r['sync'] else 'false')
        li.setProperty('hearing_imp', 'true' if r['hi'] else 'false')
        data = {'url': r['url'], 'filename': r['release'], 'lang': r['lang'], 'source': r['source']}
        url = 'plugin://%s/?action=download&data=%s' % (util.ADDON_ID, quote(json.dumps(data)))
        xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=li, isFolder=False)


def _subtitle_bytes(raw, url):
    """(bytes, extension) of a subtitle file, unpacking a zip; raises ValueError for anything else."""
    if raw[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = [n for n in z.namelist() if n.lower().rsplit('.', 1)[-1] in SUB_EXTS]
            if not names:
                raise ValueError('the zip holds no subtitle file')
            best = max(names, key=lambda n: z.getinfo(n).file_size)
            raw, url = z.read(best), best
    head = raw[:4096].lstrip(b'\xef\xbb\xbf').lstrip()
    low = head.lower()
    ext = urlparse(url).path.rsplit('.', 1)[-1].lower() if '.' in urlparse(url).path.rsplit('/', 1)[-1] else ''
    if head.startswith(b'WEBVTT'):
        return raw, 'vtt'
    if b'[script info]' in low or b'[v4+ styles]' in low or b'[v4 styles]' in low:
        return raw, 'ass'
    if b'-->' in raw[:65536] or (b'\x00-\x00-\x00>' in raw[:131072]):
        return raw, 'srt'  # also UTF-16 SRT
    if ext in ('sub', 'smi', 'txt') and not low.startswith((b'<!doctype', b'<html', b'{')):
        return raw, ext
    raise ValueError('the answer is not a subtitle file (%r...)' % head[:60])


def _safe(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', name or '').strip(' .')
    return re.sub(r'\s+', ' ', name)[:90] or 'subtitle'


def do_download(handle, p):
    try:
        data = json.loads(p.get('data') or '{}')
    except ValueError:
        data = {}
    url = data.get('url')
    if not url:
        return
    folder = util.temp_dir()
    now = time.time()
    for old in os.listdir(folder):
        try:
            if now - os.path.getmtime(os.path.join(folder, old)) > 3 * 3600:
                os.remove(os.path.join(folder, old))
        except OSError:
            pass
    start = time.time()
    try:
        # AI translations (SubMaker 'Make ...') are made while we wait: allow time for that
        raw = util.get(url, max(30, util.setting_int('timeout', 10) * 3))
        raw, ext = _subtitle_bytes(raw, url)
    except Exception as e:
        util.log('download failed from %s: %s' % (data.get('source'), e), xbmc.LOGWARNING)
        xbmcgui.Dialog().notification('SubBridge', util.addon().getLocalizedString(32020), xbmcgui.NOTIFICATION_WARNING, 3000)
        return
    lang = langs.flag(data.get('lang') or '') or data.get('lang') or 'und'
    import hashlib
    tag = hashlib.md5(url.encode('utf-8')).hexdigest()[:4]  # two results never share a file name
    path = os.path.join(folder, '%s [%s].%s.%s' % (_safe(data.get('filename')), tag, lang, ext))
    with open(path, 'wb') as fh:
        fh.write(raw)
    util.log('downloaded from %s in %.1fs: %s' % (data.get('source'), time.time() - start, os.path.basename(path)))
    xbmcplugin.addDirectoryItem(handle=handle, url=path, listitem=xbmcgui.ListItem(label=path), isFolder=False)


def main():
    handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit() else -1
    p = params()
    action = p.get('action')
    try:
        if action == 'search':
            do_search(handle, p)
        elif action == 'manualsearch':
            do_search(handle, p, manual=True)
        elif action == 'download':
            do_download(handle, p)
    except Exception as e:
        import traceback
        util.log('%s failed: %s\n%s' % (action, e, traceback.format_exc()), xbmc.LOGERROR)
    if handle >= 0:
        xbmcplugin.endOfDirectory(handle)


if __name__ == '__main__':
    main()
