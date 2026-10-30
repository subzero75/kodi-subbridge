"""Language codes: Stremio add-ons send ISO 639-2 codes (with a few OpenSubtitles extras
such as 'pob' for Brazilian Portuguese), sometimes two-letter codes or plain text."""
import re

import xbmc

# OpenSubtitles' own codes and ISO 639-2/T codes -> the ISO 639-2/B codes Kodi uses
ALIASES = {
    'pob': 'por', 'pb': 'por', 'pt-br': 'por', 'pt_br': 'por',
    'spn': 'spa', 'ea': 'spa', 'es-419': 'spa', 'es-la': 'spa', 'es-mx': 'spa',
    'zht': 'chi', 'zhe': 'chi', 'ze': 'chi', 'zho': 'chi', 'zh-tw': 'chi', 'zh-cn': 'chi',
    'zh-hk': 'chi', 'zh-hans': 'chi', 'zh-hant': 'chi',
    'scc': 'srp', 'mne': 'srp', 'ell': 'gre', 'fas': 'per', 'deu': 'ger', 'fra': 'fre',
    'nld': 'dut', 'ces': 'cze', 'slk': 'slo', 'ron': 'rum', 'sqi': 'alb', 'hye': 'arm',
    'eus': 'baq', 'kat': 'geo', 'isl': 'ice', 'mkd': 'mac', 'msa': 'may', 'mya': 'bur',
    'bod': 'tib', 'cym': 'wel', 'iw': 'heb', 'in': 'ind', 'ji': 'yid',
}
VARIANTS = {
    'pob': 'Brazil', 'pb': 'Brazil', 'pt-br': 'Brazil', 'pt_br': 'Brazil',
    'spn': 'Latin America', 'ea': 'Latin America', 'es-419': 'Latin America',
    'es-la': 'Latin America', 'es-mx': 'Latin America',
    'zht': 'Traditional', 'zh-tw': 'Traditional', 'zh-hk': 'Traditional', 'zh-hant': 'Traditional',
    'zhe': 'Bilingual', 'ze': 'Bilingual', 'zh-cn': 'Simplified', 'zh-hans': 'Simplified',
}
# Kodi's flag images for the variants
FLAGS = {'Brazil': 'pb'}


def code(text):
    """('ara', '') for 'ara' / 'ar' / 'Arabic'; ('por', 'Brazil') for 'pob'; ('', '') when unknown."""
    t = (text or '').strip().lower()
    if not t:
        return '', ''
    if t in ALIASES:
        return ALIASES[t], VARIANTS.get(t, '')
    if len(t) <= 3 or re.match(r'^[a-z]{2,3}[-_][a-z0-9]{2,4}$', t):
        base = re.split(r'[-_]', t)[0]
        found = xbmc.convertLanguage(base, xbmc.ISO_639_2)
    else:
        found = xbmc.convertLanguage(text.strip(), xbmc.ISO_639_2)  # an English name
    found = (found or '').lower()
    return ALIASES.get(found, found), ''


def name(c, variant=''):
    """'Arabic', 'Portuguese (Brazil)'"""
    n = xbmc.convertLanguage(c, xbmc.ENGLISH_NAME) or c
    return '%s (%s)' % (n, variant) if variant else n


def flag(c, variant=''):
    """Two-letter code Kodi shows a flag for."""
    return FLAGS.get(variant) or xbmc.convertLanguage(c, xbmc.ISO_639_1) or ''


def in_text(text, wanted):
    """A wanted language named in free text ('Make Arabic', 'xSync English'), or ''."""
    for c in wanted:
        n = xbmc.convertLanguage(c, xbmc.ENGLISH_NAME)
        if n and re.search(r'(?<![a-z])%s(?![a-z])' % re.escape(n.lower()), text.lower()):
            return c
    return ''


def wanted(names):
    """Kodi's language list ('English,Arabic' or codes) -> ['eng', 'ara'] in order."""
    out = []
    for n in names:
        c = code(n)[0]
        if c and c not in out:
            out.append(c)
    return out
