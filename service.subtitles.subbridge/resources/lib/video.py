"""What is playing: movie or episode, its IMDb id, and file details for exact matches."""
import json
import os
import re
import struct
from urllib.parse import quote_plus, unquote

import xbmc
import xbmcvfs

from resources.lib import util

VIDEO_EXTS = ('.strm', '.mkv', '.mp4', '.avi', '.ts', '.m2ts', '.mov', '.webm', '.wmv', '.m4v', '.mpg')
NAME_SXXEYY = re.compile(r'^(.*?)[\s._\-\[(]+s(\d{1,2})[\s._-]?e(\d{1,4})(?!\d)', re.I)
NAME_NXNN = re.compile(r'^(.*?)[\s._\-\[(]+(\d{1,2})x(\d{2,3})(?!\d)', re.I)
NAME_YEAR = re.compile(r'^(.*?)[\s._\-\[(]+((?:19|20)\d\d)(?!\d)')
SEASON_DIR = re.compile(r'^(?:season|series|staffel|saison|temporada|stagione|seizoen|sezon|s)[\s._-]*(\d{1,2})$', re.I)
EPISODE_ONLY = re.compile(r'^(?:e|ep|episode|\#)?[\s._-]*(\d{1,4})(?!\d)', re.I)
JUNK = re.compile(r'\b(?:2160p|1080p|720p|480p|4k|uhd|hdr|web[\s.-]?dl|webrip|bluray|bdrip|remux|x26[45]|h\.?26[45]|hevc)\b.*$', re.I)
IMDB = re.compile(r'^tt\d{5,}$')


def _clean(text):
    """'[Group] The.Matrix.Reloaded_' -> 'The Matrix Reloaded'"""
    text = re.sub(r'^\s*\[[^\]]*\]\s*', '', text or '')
    text = re.sub(r'[._]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip(' -([)]')


def _number(label):
    m = re.match(r'^\s*(\d+)\s*$', label or '')
    return int(m.group(1)) if m else None


def imdb_from_title(title, year=None, movie=False):
    """IMDb id of a series (or movie) title from IMDb's search suggestions; '' when unsure."""
    query = re.sub(r'[^a-z0-9]+', '_', (title or '').strip().lower()).strip('_')[:20]
    if not query:
        return ''
    url = 'https://v2.sg.media-imdb.com/suggestion/%s/%s.json' % (quote_plus(query[0]), quote_plus(query))
    try:
        found = util.get_json(url, 8).get('d') or []
    except Exception as e:
        util.log('IMDb lookup for "%s" failed: %s' % (title, e), xbmc.LOGWARNING)
        return ''
    kinds = ('feature', 'TV movie', 'video') if movie else ('TV series', 'TV mini-series')
    want = re.sub(r'[^a-z0-9]+', ' ', title.lower()).strip()
    hits = [d for d in found if d.get('q') in kinds and IMDB.match(d.get('id', ''))
            and re.sub(r'[^a-z0-9]+', ' ', (d.get('l') or '').lower()).strip() == want]
    if year:
        dated = [d for d in hits if d.get('y') == int(year)]
        if movie and not dated:
            # a movie of the same name from another year is another movie
            dated = [d for d in hits if abs((d.get('y') or 0) - int(year)) <= 1]
            hits = dated
        hits = dated or hits
    if not hits:
        util.log('IMDb lookup: no %s called "%s"' % ('movie' if movie else 'series', title))
        return ''
    best = min(hits, key=lambda d: d.get('rank') or 10 ** 9)
    util.log('IMDb lookup: "%s" -> %s (%s %s)' % (title, best['id'], best.get('l'), best.get('y')))
    return best['id']


def _split(path):
    """(folder names, file name without extension) of a playing path."""
    path = (path or '').split('?')[0].split('|')[0].replace('\\', '/')
    parts = [unquote(p) for p in path.split('/') if p]
    if not parts:
        return [], ''
    name = parts[-1]
    if name.lower().endswith(VIDEO_EXTS):
        name = os.path.splitext(name)[0]
    return parts[:-1], name


def _from_names(path, names):
    """{'kind', 'title', 'year', 'season', 'episode'} from file and folder names, or None.
    Episodes: 'Lost S01E25 ...', 'Lost 1x25 ...', 'Lost/Season 1/25 - Exodus.mkv'.
    Movies: 'The.Matrix.1999.1080p.mkv'."""
    dirs, fname = _split(path)
    local = path and not path.startswith(('http', 'plugin:'))
    names = [n for n in names + [fname] if n]
    for name in names:
        for rx in (NAME_SXXEYY, NAME_NXNN):
            m = rx.search(' ' + name)
            if not m:
                continue
            show = _clean(m.group(1))
            if not show and dirs and local:
                # 'S01E05.mkv' in a folder named after the show
                show = _clean(next((d for d in reversed(dirs) if not SEASON_DIR.match(d.strip())), ''))
            if show:
                y = NAME_YEAR.search(show)
                return {'kind': 'series', 'title': _clean(NAME_YEAR.sub(r'\1', show)) or show,
                        'year': y.group(2) if y else '', 'season': int(m.group(2)), 'episode': int(m.group(3))}
    if len(dirs) >= 2 and local:
        sm = SEASON_DIR.match(dirs[-1].strip())
        em = EPISODE_ONLY.match(fname.strip())
        if sm and em:
            return {'kind': 'series', 'title': _clean(dirs[-2]), 'year': '',
                    'season': int(sm.group(1)), 'episode': int(em.group(1))}
    for name in names:
        y = NAME_YEAR.search(name)
        if y and _clean(y.group(1)):
            return {'kind': 'movie', 'title': _clean(JUNK.sub('', y.group(1))), 'year': y.group(2)}
    return None


def _library_show_imdb(tag):
    """IMDb id of the show of a library episode."""
    show_id = _number(xbmc.getInfoLabel('VideoPlayer.TvShowDBID'))
    if not show_id and tag is not None:
        try:
            if tag.getMediaType() == 'episode' and tag.getDbId() > 0:
                ep = util.rpc('VideoLibrary.GetEpisodeDetails',
                              {'episodeid': tag.getDbId(), 'properties': ['tvshowid']})
                show_id = (ep.get('episodedetails') or {}).get('tvshowid')
        except Exception:
            pass
    if not show_id or show_id < 0:
        return ''
    show = util.rpc('VideoLibrary.GetTVShowDetails', {'tvshowid': show_id, 'properties': ['uniqueid', 'imdbnumber']})
    d = show.get('tvshowdetails') or {}
    for v in [(d.get('uniqueid') or {}).get('imdb'), d.get('imdbnumber')]:
        if v and IMDB.match(v):
            return v
    return ''


def playing():
    """Facts about the playing video:
    {'kind': 'movie'|'series', 'ids': [IMDb ids to try, best first], 'title', 'year',
     'season', 'episode', 'path', 'lookup': (title, year) still to look up or None}"""
    player = xbmc.Player()
    path = ''
    tag = None
    try:
        path = player.getPlayingFile()
        tag = player.getVideoInfoTag()
    except Exception:
        pass
    imdb = xbmc.getInfoLabel('VideoPlayer.IMDBNumber')
    if tag is not None and not IMDB.match(imdb or ''):
        try:
            imdb = tag.getUniqueID('imdb') or tag.getIMDBNumber()
        except Exception:
            pass
    imdb = imdb if IMDB.match(imdb or '') else ''
    show = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
    season = _number(xbmc.getInfoLabel('VideoPlayer.Season'))
    episode = _number(xbmc.getInfoLabel('VideoPlayer.Episode'))
    title = xbmc.getInfoLabel('VideoPlayer.OriginalTitle') or xbmc.getInfoLabel('VideoPlayer.Title')
    year = xbmc.getInfoLabel('VideoPlayer.Year')
    info = {'path': path, 'ids': [], 'lookup': None}

    if season is not None and episode is not None and (show or episode > 0):
        info.update(kind='series', title=show or title, year=year, season=season, episode=episode)
        # Kodi's IMDb id of an episode is sometimes the episode's own id: the show's comes first
        info['ids'] = [i for i in (_library_show_imdb(tag), imdb) if i]
        if show:
            info['lookup'] = (show, '')
    elif imdb:
        info.update(kind='movie', title=title, year=year, ids=[imdb])
    else:
        guess = _from_names(path, [xbmc.getInfoLabel('VideoPlayer.Title'), xbmc.getInfoLabel('Player.Filename')])
        if guess:
            info.update(guess)
            info['lookup'] = (guess['title'], guess['year'])
            util.log('no IMDb id, from the name: %s' % json.dumps(guess))
        elif title:
            info.update(kind='movie', title=title, year=year, lookup=(title, year))
        else:
            info.update(kind='movie', title='', year='')
    return info


def from_search_string(text):
    """Manual search: 'Lost S01E25', 'The Matrix 1999' or just 'The Matrix'."""
    text = (text or '').strip()
    guess = _from_names('', [text])
    if guess:
        return dict(guess, ids=[], path='', lookup=(guess['title'], guess['year']))
    return {'kind': 'movie', 'title': text, 'year': '', 'ids': [], 'path': '', 'lookup': (text, '')}


def stremio_id(info, imdb):
    if info['kind'] == 'series':
        return '%s:%d:%d' % (imdb, info['season'], info['episode'])
    return imdb


def file_details(path, use_hash=True):
    """{'filename', 'videoSize', 'videoHash'} for exact matches. Hash and size only for files
    Kodi reads directly (local, SMB, NFS), never for internet streams."""
    raw = unquote((path or '').split('?')[0].split('|')[0].replace('\\', '/').rsplit('/', 1)[-1])
    extra = {}
    if raw and raw.lower().endswith(VIDEO_EXTS[1:]):
        extra['filename'] = raw
    else:
        fn = xbmc.getInfoLabel('Player.Filename')
        if fn and fn.lower().endswith(VIDEO_EXTS[1:]):
            extra['filename'] = fn
    if use_hash and path and not path.startswith(('http', 'plugin:', 'pvr:', 'upnp:')):
        try:
            h, size = opensubtitles_hash(path)
            if h:
                extra['videoHash'], extra['videoSize'] = h, size
        except Exception as e:
            util.log('file hash failed: %s' % e, xbmc.LOGWARNING)
    return extra


def opensubtitles_hash(path):
    """The OpenSubtitles movie hash: size + sums of the first and last 64 KB."""
    block = 65536
    f = xbmcvfs.File(path)
    try:
        size = f.size()
        if size < 2 * block:
            return '', size
        head = bytes(f.readBytes(block))
        f.seek(size - block, 0)
        tail = bytes(f.readBytes(block))
    finally:
        f.close()
    if len(head) < block or len(tail) < block:
        return '', size
    h = size
    for chunk in (head, tail):
        h += sum(struct.unpack('<%dQ' % (block // 8), chunk))
    return '%016x' % (h & 0xFFFFFFFFFFFFFFFF), size
