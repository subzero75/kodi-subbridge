"""Talking to Stremio subtitle add-ons.

A Stremio add-on is a base URL. Its manifest is at <base>/manifest.json, and its subtitles
for a video at <base>/subtitles/<movie|series>/<id>[/<extra>].json, where <id> is an IMDb id
('tt0133093') or, for an episode, 'tt0411008:1:25', and <extra> is optional
'filename=...&videoHash=...&videoSize=...'. The answer is {"subtitles": [{"id", "url",
"lang", "label"?}, ...]}."""
import re
import threading
import time
from urllib.parse import quote, urlparse

import xbmc
import xbmcvfs

from resources.lib import util

OPENSUBTITLES = 'https://opensubtitles-v3.strem.io'
MANIFEST_DAYS = 7


def normalize(link):
    """Any form of an install link -> its base URL, or ''.
    'stremio://host/abc/manifest.json' -> 'https://host/abc'"""
    link = (link or '').strip().strip('\'"<>')
    if link.lower().startswith('stremio://'):
        rest = link[len('stremio://'):]
        host = rest.split('/')[0].split(':')[0].lower()
        # Stremio opens stremio:// links over https, except add-ons on the home network
        home = (host in ('localhost',) or host.endswith('.local') or re.match(
            r'^(?:127\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)', host))
        link = ('http://' if home else 'https://') + rest
    if not re.match(r'(?i)^https?://[^/\s]+', link):
        return ''
    link = link.split('#')[0].rstrip('/')
    for tail in ('/manifest.json', '/configure'):
        if link.lower().endswith(tail):
            link = link[:-len(tail)].rstrip('/')
    return link


def links():
    """Base URLs to ask, in order: OpenSubtitles v3 (when on), the links setting, the links file."""
    found = []
    if util.setting_bool('opensubtitles', True):
        found.append(OPENSUBTITLES)
    text = util.setting('links')
    path = util.setting('links_file')
    if path:
        try:
            f = xbmcvfs.File(path)
            text += '\n' + f.read()
            f.close()
        except Exception as e:
            util.log('could not read the links file %s: %s' % (path, e), xbmc.LOGWARNING)
    for line in text.splitlines():
        line = line.split(' #')[0].strip()
        if line.startswith('#'):
            continue
        for word in line.split():
            base = normalize(word)
            if base and base not in found:
                found.append(base)
    return found


def short_name(base):
    """'opensubtitles-v3.strem.io' -> 'opensubtitles-v3'; used until the manifest is known."""
    host = urlparse(base).netloc.split('@')[-1].split(':')[0]
    if re.match(r'^[\d.]+$', host) or host == 'localhost':
        return host
    parts = host.split('.')
    return parts[0] if len(parts) > 2 and parts[0] not in ('www', 'api') else parts[-2] if len(parts) > 1 else host


def _manifest(base, timeout):
    m = util.get_json(base + '/manifest.json', timeout)
    res = m.get('resources') or []
    subs = [r for r in res if r == 'subtitles' or (isinstance(r, dict) and r.get('name') == 'subtitles')]
    entry = next((r for r in subs if isinstance(r, dict)), {})
    return {
        'name': (m.get('name') or '').strip() or short_name(base),
        'subtitles': bool(subs) or not res,
        'types': entry.get('types') or m.get('types') or [],
        'prefixes': entry.get('idPrefixes') or m.get('idPrefixes') or [],
    }


def _accepts(info, kind, vid):
    if not info:
        return True
    if not info.get('subtitles'):
        return False
    if info.get('types') and kind not in info['types']:
        return False
    if info.get('prefixes') and not any(vid.startswith(p) for p in info['prefixes']):
        return False
    return True


def extra_part(extra):
    """{'filename': 'a b.mkv', 'videoSize': 5} -> 'filename=a%20b.mkv&videoSize=5'"""
    return '&'.join('%s=%s' % (k, quote(str(v), safe='')) for k, v in extra.items() if v)


def _ask(base, kind, vid, extra, timeout):
    path = '%s/subtitles/%s/%s' % (base, kind, quote(vid, safe=':'))
    ex = extra_part(extra)
    try:
        data = util.get_json(path + ('/' + ex if ex else '') + '.json', timeout)
    except Exception as e:
        if not ex or 'timed out' in str(e).lower():
            raise
        # some add-ons cannot handle the extra part: ask again without it
        util.log('%s: %s with file details, asking without them' % (base, e))
        data = util.get_json(path + '.json', timeout)
    subs = data.get('subtitles') if isinstance(data, dict) else None
    return [s for s in (subs or []) if isinstance(s, dict) and s.get('url')]


class _Job(threading.Thread):
    """Runs fn(*args) in the background. Daemon, so a link that hangs never keeps Kodi's
    Python waiting after the results are shown."""

    def __init__(self, fn, *args):
        super().__init__(daemon=True)
        self.fn, self.args, self.result, self.error = fn, args, None, None
        self.start()

    def run(self):
        try:
            self.result = self.fn(*self.args)
        except Exception as e:
            self.error = e


def search(kind, vid, extra, timeout):
    """[(base, add-on name, [subtitle dicts]) per link], asking all links at the same time.
    Links that fail or take longer than timeout give an empty list."""
    bases = links()
    manifests = util.Store('manifests.json', MANIFEST_DAYS * 86400)
    known = {b: manifests.get(b) for b in bases}
    todo = [b for b in bases if _accepts(known[b], kind, vid)]
    skipped = [b for b in bases if b not in todo]
    if skipped:
        util.log('not asked (their manifest does not offer %s subtitles for %s): %s' % (kind, vid, skipped))
    results = {b: [] for b in todo}
    start = time.time()
    asks = {b: _Job(_ask, b, kind, vid, extra, timeout) for b in todo}
    learn = {b: _Job(_manifest, b, timeout) for b in bases if known[b] is None}
    jobs = list(asks.values()) + list(learn.values())
    for job in jobs:
        job.join(max(0.1, start + timeout + 1 - time.time()))
    for b, job in asks.items():
        if job.is_alive():
            util.log('%s: no answer in %ds' % (b, timeout), xbmc.LOGWARNING)
        elif job.error:
            util.log('%s: %s' % (b, job.error), xbmc.LOGWARNING)
        else:
            results[b] = job.result
    for b, job in learn.items():
        if not job.is_alive() and not job.error:
            known[b] = job.result
            manifests.put(b, known[b])
    manifests.save()
    util.log('%s %s: %s in %.1fs' % (kind, vid, ', '.join(
        '%s %d' % ((known.get(b) or {}).get('name') or short_name(b), len(results[b])) for b in todo),
        time.time() - start))
    return [(b, (known.get(b) or {}).get('name') or short_name(b), results[b]) for b in todo]
