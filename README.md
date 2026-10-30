# SubBridge

A Kodi subtitle add-on that gets subtitles from **Stremio subtitle add-ons**. It sends each add-on one quick request, and the add-on's server does the searching. Subtitles usually show up in about a second.

- **Works right after installing.** It uses Stremio's official, free OpenSubtitles v3 add-on, with no account, key or setup.
- **Any other Stremio or Nuvio subtitle add-on** can be added by pasting its install link (SubMaker, SubSource, Wyzie and others).
- **Shows up as a normal Kodi subtitle add-on**, so it works with every video add-on, with Kodi's own subtitle search, and with [Subtitle Cycler](https://github.com/subzero75/kodi-subtitle-cycler).
- **Covers all languages**: it follows the subtitle languages set in Kodi (Settings → Player → Language).

## Install

1. Download `service.subtitles.subbridge-x.y.z.zip` from [Releases](../../releases).
2. In Kodi go to Add-ons → Install from zip file, and pick the zip.
3. Play something, open the subtitle menu and choose **Download** → **SubBridge**.

## Adding more Stremio subtitle add-ons (optional)

1. Set up the add-on on its own website, as you would for Stremio or Nuvio.
2. Copy the install link it gives you. Both forms work:
   `https://…/manifest.json` and `stremio://…/manifest.json`.
3. In SubBridge's settings, paste it into **Extra Stremio subtitle links**. To add several, separate them with spaces.

Long links are hard to type with a remote, so there are two easier ways:

- **Paste from your phone** with the Kore or Yatse app's keyboard while the text box is open on the TV.
- **Use a text file.** Put one link per line in a text file, copy it to the device, and choose it under **File with more links**. Lines that start with `#` are ignored.

> Install links of configured add-ons usually contain your settings and API keys. Treat them like passwords and don't post them publicly.

## Settings

| Setting | Default | What it does |
|---|---|---|
| Use OpenSubtitles v3 | On | Stremio's official OpenSubtitles add-on, free, no account |
| Extra Stremio subtitle links | empty | More add-ons, separated by spaces |
| File with more links | empty | A text file with one link per line |
| Wait for each link | 10 s | All links are asked at once; slower ones are skipped for that search |
| Show all languages | Off | Off: only your Kodi subtitle languages |
| Send file details of local files | On | For files on the device or home network: sends the OpenSubtitles hash and size for exact matches. Never done for internet streams |

## How it finds the video

SubBridge asks Stremio add-ons by IMDb id (`tt0411008`, or `tt0411008:1:25` for an episode). It uses, in order:

1. The IMDb id of the show from Kodi's library, for library episodes.
2. The IMDb id Kodi or the video add-on gives for what's playing.
3. A lookup of the title (and year) on IMDb, for videos without an id: `.strm` files, links played from a file list, and local files named like `Show S01E05`, `Show/Season 1/05.mkv` or `Movie 1999`.

It always sends the file name, so add-ons that compare release names can pick the best match. A result whose name matches the playing file is marked as synced and listed first.

## What it can't do

- Results are only as good as the add-ons you use. With only OpenSubtitles v3, you get what OpenSubtitles has.
- Most add-ons match by IMDb id and episode, not the exact release, so timing can be off. Subtitle Cycler's sync option fixes most of that.
- Add-ons that only offer subtitles from inside torrents on Stremio's own streaming server are skipped.

## License

MIT. SubBridge only talks to the add-ons you choose; it contains no code from them.
