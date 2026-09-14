# The Frontier Podcast — OBS studio, as code

A two-person remote podcast studio for OBS on macOS, generated from Python
rather than clicked together by hand. A broadcast-style scene collection, a
remote guest over WebRTC with two independent feeds, four-track audio, and a
test suite that holds the whole thing in place.

Built for one show, but the interesting parts — the generator, the audio
routing, the guest transport — transfer to any two-person remote setup.

## Why generate the scenes?

An OBS scene collection is a 190 KB JSON file. Laying out nine scenes by
dragging boxes means nine chances to be three pixels off, and no way to tell
afterwards. Generating it means the layout is described once, arithmetic is
done by a computer, and the result can be asserted on:

```
Ran 68 tests in 41.966s
OK
```

Those tests check real properties — cells never overlap, borders sit exactly
3px behind their feed, the 9:16 safe zone is respected, no two sources claim
the same audio track, every scene keeps the guest audible. Several of them
exist because the corresponding bug actually happened.

## What you get

Nine scenes on F1–F10:

| Key | Scene | |
|---|---|---|
| F1 | 01 Intro | Title card |
| F2 | 02 Solo — Me | |
| F3 | 03 Solo — Guest | |
| F4 | 04 Two Shot | Side by side |
| F5 | 05 Screen — 3 Column | Guest · content · me |
| F6 | 06 Screen Full | Content edge to edge |
| F8 | 08 Screen + Guest | |
| F9 | 09 Two Shot — Over/Under | Vertical-safe, for clips |
| F10 | 10 Outro | |

Plus a top bar with a live clock, a lower stack with a rotating sponsor
ticker, an animated starfield, and a tenth hidden scene (`SLOT — Content`)
that switches between your screen and the guest's with one toggle.

## Requirements

- macOS, OBS 30+
- Python 3.9+ (standard library only — no pip install)
- ffmpeg, for `verify_recording.sh`
- Your guest: a **Chromium** browser on a laptop. Not a phone — every iOS
  browser is Safari underneath and loses the local recording when the screen
  locks.

## Setup

```bash
cp .env.example .env && chmod 600 .env
# fill in the three values, using the openssl lines in the file
set -a && . ./.env && set +a

python3 build_scenes.py                 # writes podcast_scenes.json
python3 build_scenes.py --guest-link    # prints the link for your guest
```

Install it (quit OBS first — it rewrites its config on exit):

```bash
cp podcast_scenes.json ~/Library/"Application Support"/obs-studio/basic/scenes/Frontier_Podcast.json
./apply_profile.sh
```

Then in OBS: **Settings → Output → Recording** → Rate Control **CRF**,
Quality **80**, and tick Audio Tracks **1, 2, 3, 6**. Those two can't be
scripted — OBS keeps encoder properties in a separate per-encoder file.

macOS will also need OBS granted **Input Monitoring** and **Accessibility**
in System Settings → Privacy & Security, or the function-key hotkeys never
fire.

## How the remote guest works

No Riverside, no Zencastr, no screen-capturing a call window.
[VDO.Ninja](https://vdo.ninja) (open source) carries the guest as **two
independent streams** — camera and screen share — so a three-column layout
with their face, their screen and yours is actually possible. Capturing a
call window can't do this: the guest's face and their share are the same
window.

```
guest's browser  ──push──▶  vdo.ninja  ──view──▶  OBS browser sources
      │                                               (receive only)
      └─ &record: pristine local file on their disk
```

Three pieces, each with a job:

- **OBS** receives and records. It never plays guest audio out loud.
- **Your director tab** (`?director=ROOM`, open in Chrome, headphones on) is
  the talkback path. It is how your guest hears you and how you hear them.
  The OBS sources are receive-only and send nothing back.
- **The guest's browser** streams to you *and* writes a full-quality local
  file via `&record`. The stream is compressed to survive the network; that
  file isn't. Clap at the top of the episode and swap the clean file in
  during the edit — a double-ender, so the episode's quality doesn't depend
  on anyone's wifi.

Send your guest [GUEST.md](GUEST.md). It covers everything they need.

## Audio

Four tracks, so the recording stays fixable:

| Track | Source |
|---|---|
| 1 | Your mic, isolated |
| 2 | Guest's voice, isolated |
| 3 | Audio from whatever the guest shares |
| 6 | Safety mix of all three |

Two things in the design look like bugs and are not:

**Monitoring is off on every source.** You hear the guest in the director
tab. If OBS monitored as well you'd hear the same voice twice, a few hundred
milliseconds apart — that combs rather than adds.

**Every scene contains invisible full-canvas copies of the guest sources.**
OBS only activates a source's audio while it is in the program scene *and*
visible; hidden is exactly as silent as absent. Without these "carriers"
pinned under the opaque backing layer, the guest goes mute the moment you cut
to a scene with no guest cell — and since the page stays connected, nothing
looks wrong until you open the edit.

After a recording:

```bash
./verify_recording.sh            # newest file in ~/Movies
```

It reports each track's mean and peak level and fails if one is silent.
Digital silence reads as −91 dB; speech sits far above the −80 dB threshold.

## Identifiers

**Use alphanumeric room names and stream IDs. No hyphens.**

VDO.Ninja sanitises stream IDs in the guest's browser after the page loads —
[the docs](https://docs.vdo.ninja/getting-started/stream-ids) state that
non-alphanumeric characters become `_`. A guest handed `guest-1234` publishes
as `guest_1234`, while OBS keeps subscribing to the hyphenated form.

Nothing errors. The guest appears in the director tab, OBS renders a
video-shaped placeholder that looks like a connected-but-blank camera, and
both sources show up in the audio mixer. Every surface says the connection is
live. This cost an hour of debugging browsers and camera permissions before
anyone thought to compare the two IDs.

`stream_id()` now applies the same rule at the single point both links derive
from, so the two ends can't disagree. `check_room()` rejects non-alphanumeric
rooms outright rather than relying on behaviour the docs leave undefined.

## Secrets

A VDO.Ninja room is unauthenticated — anyone with the room name can walk into
a live recording. The password is the only thing standing in the way.

Four generated files embed those values in plaintext and are all gitignored:
`.env`, `guest_link.txt`, `director_link.txt`, `view_link.txt`, along with the
built `podcast_scenes.json`. Regenerate rather than share, and send the guest
link over a private channel.

`build_scenes.py` has **no default room** on purpose. A placeholder would let
an unset variable produce a *successful* build pointing at a real, guessable,
public room — a silent misconfiguration far worse than a crash.

## Layout

```
build_scenes.py       generator — scenes, layout, URLs, audio routing
test_scenes.py        68 tests, including headless-Chrome asset renders
apply_profile.sh      OBS recording profile (multitrack, hardware encode)
verify_recording.sh   per-track silence check on a finished recording
assets/               HTML/CSS overlays: top bar, lower stack, cards, starfield
GUEST.md              send this to your guest
```

Tests, including the ones that render the real HTML overlays in headless
Chrome and assert on pixels:

```bash
python3 -m unittest test_scenes -v
```

## Editing the layout

Change the constants at the top of `build_scenes.py` (`CANVAS_W`, `BAND_Y`,
`MARGIN`, `GAP`, `BORDER`), or the `c.scene(...)` calls, then rebuild. Don't
drag items around inside OBS — the next rebuild overwrites them, and the
geometry tests won't know.

## License

MIT
