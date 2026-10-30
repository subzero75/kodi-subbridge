import gzip
import json
import os
import time
import zlib
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_ID = 'service.subtitles.subbridge'
UA = 'Mozilla/5.0 (Kodi; SubBridge)'


def addon():
    return xbmcaddon.Addon(ADDON_ID)


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[SubBridge] %s' % msg, level)


def setting(key, default=''):
    try:
        return addon().getSetting(key)
    except Exception:
        return default


def setting_bool(key, default=False):
    try:
        return addon().getSettingBool(key)
    except Exception:
        return default


def setting_int(key, default=0):
    try:
        return addon().getSettingInt(key)
    except Exception:
        return default


def profile_dir():
    path = xbmcvfs.translatePath(addon().getAddonInfo('profile'))
    os.makedirs(path, exist_ok=True)
    return path


def temp_dir():
    path = os.path.join(xbmcvfs.translatePath('special://temp'), 'subbridge')
    os.makedirs(path, exist_ok=True)
    return path


def get(url, timeout, accept='*/*'):
    """Bytes of a URL (gzip/deflate undone)."""
    req = Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Encoding': 'gzip, deflate'})
    with urlopen(req, timeout=timeout) as r:
        data = r.read()
        enc = (r.headers.get('Content-Encoding') or '').lower()
    if enc == 'gzip' or data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    elif enc == 'deflate':
        try:
            data = zlib.decompress(data)
        except zlib.error:
            data = zlib.decompress(data, -zlib.MAX_WBITS)
    return data


def get_json(url, timeout):
    return json.loads(get(url, timeout, 'application/json').decode('utf-8', 'replace'))


def rpc(method, params=None):
    q = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
    try:
        return json.loads(xbmc.executeJSONRPC(json.dumps(q))).get('result') or {}
    except Exception:
        return {}


class Store:
    """A small JSON file in the add-on's profile folder, entries kept for max_age seconds."""

    def __init__(self, name, max_age):
        self.path = os.path.join(profile_dir(), name)
        self.max_age = max_age
        try:
            with open(self.path, encoding='utf-8') as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}
        now = time.time()
        self.data = {k: v for k, v in self.data.items()
                     if isinstance(v, dict) and now - v.get('t', 0) < max_age}

    def get(self, key):
        v = self.data.get(key)
        return v.get('v') if v else None

    def put(self, key, value):
        self.data[key] = {'t': time.time(), 'v': value}

    def save(self):
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(self.data, fh)
            os.replace(tmp, self.path)
        except Exception as e:
            log('could not save %s: %s' % (self.path, e), xbmc.LOGWARNING)
