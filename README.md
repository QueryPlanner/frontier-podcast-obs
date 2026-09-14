# What’s the Frontier · OBS studio

A podcast studio for Chirag and Parth, with an optional third participant.
Each generated collection opens on **04 Duo**. It includes twelve scenes,
separate remote camera and screen feeds, six audio tracks, and a local preview.

The design uses the WTF brand board: Event Horizon `#07080D`, Signal Bone
`#F2EBDD`, Spectral `#8B7CFF`, Orbital Heat `#FF9D62`, and Deep Field
`#162752`. Dela Gothic One is reserved for the WTF mark, Anybody handles
headlines and readable body copy, and Fragment Mono handles metadata.
All three fonts are bundled locally with their licenses.

Host identities show **lordpatil.com** for Chirag and **parthshastri.co.in** for Parth.
**Lord Socks**, **House of Lords** and the supplied **Bev. SVG logo** appear together in a shared brand strip, separate from either host.
The Bev. artwork is preserved without redrawing or substituting typed text.

## Preview the studio

```bash
python3 preview_studio.py
open render/studio-preview.html
```

The preview uses the actual scene geometry and HTML overlays. Its camera and
shared-content placeholders are illustrative. It never opens cameras,
microphones or remote feeds, and it needs no credentials. Choose a scene from
the menu or use F1 through F12.

## Scenes

| Key | Scene | Purpose |
| --- | --- | --- |
| F1 | 01 Standby | Animated WTF logo and starting-soon card |
| F2 | 02 Solo · Chirag | Chirag’s camera |
| F3 | 03 Solo · Parth | Parth’s camera |
| F4 | 04 Duo | Default view with Chirag and Parth |
| F5 | 05 Screen · Duo | Large shared content with both hosts |
| F6 | 06 Screen Full | Shared content fitted within the broadcast frame |
| F7 | 07 Trio · With Guest | Chirag, Parth and the guest side by side |
| F8 | 08 Screen · Trio | Large shared content with all three participants |
| F9 | 09 Duo · Vertical | Stacked host cameras spanning the vertical safe zone |
| F10 | 10 Outro | Closing card with both hosts and the shared brand strip |
| F11 | 11 Solo · Guest | Guest camera |
| F12 | 12 Break | Animated standby card reading “Back shortly” |

The hidden **SLOT · Content** scene holds the local screen, Parth’s screen and
the guest’s screen. Enable exactly one source in that slot to choose what all
screen-sharing scenes display. Shared content fits its frame without cropping.

The canvas is 1920 × 1080. The top strip occupies 96 pixels and the lower panel
196 pixels, leaving a 756-pixel camera band with breathing room above and below.
Camera name labels stay attached to their corresponding feeds in every layout.

## Choose the local host in OBS

Import the two generated collections once, then select the local host from
OBS’s **Scene Collection** menu before recording:

- **WTF · Chirag local** uses Chirag’s local camera and microphone. Parth joins remotely.
- **WTF · Parth local** uses Parth’s local camera and microphone. Chirag joins remotely.

Both choices have the same duo default, guest scenes, layouts and branding.
The optional guest always has an independent feed. This uses OBS’s native
[Scene Collections](https://obsproject.com/kb/scene-collections) feature and
requires no additional OBS plugin.

Assign your camera and microphone once in the chosen collection’s **CAM** and
**MIC** sources named after you. Assign the local screen in **SCREEN · Share**.
Hardware IDs are intentionally unset so the collection can be imported on
either host’s computer. Select the collection before starting a recording;
changing collections replaces sources and reconnects the remote feeds.

The local operator uses the VDO.Ninja director tab, with headphones, for
talkback with the remote cohost and guest. Remote sources are receive-only
and do not restart when switching scenes within a collection. OBS monitoring
stays off to avoid hearing a second copy.

## Generate the collection

Requirements: macOS with OBS, Python 3.9 or later, and a Chromium browser for
remote participation. Node is needed only for browser verification.

```bash
cp .env.example .env
chmod 600 .env
```

Fill in `VDO_ROOM`, `VDO_CHIRAG_ID`, `VDO_PARTH_ID`, `VDO_GUEST_ID` and
`VDO_PASSWORD` using the examples in that file. Give all three people distinct
stream IDs, including on episodes without a guest.

```bash
set -a
. ./.env
set +a

python3 build_scenes.py --both-local-hosts --episode 01 --title "Conversations at the edge of possible"
python3 build_scenes.py --parth-link
python3 build_scenes.py --chirag-link
python3 build_scenes.py --guest-link
```

The dual build creates `podcast_scenes_chirag_local.json` and
`podcast_scenes_parth_local.json`. Send the remote cohost their corresponding
invitation. The local operator uses the director tab rather than their own
remote invitation.

To generate only one variant, use `--local-host chirag` or `--local-host parth`.
This writes `podcast_scenes.json` and requires only the remote cohost’s ID and
the guest ID. The original command without a host flag still defaults to
Chirag local for compatibility.

For a guest episode, include `--guest-name "Guest Name"` and
`--guest-role "Guest role"`. These update the camera labels.

The generator rejects missing IDs, invalid room names and participant IDs
that become identical after normalization. Real credentials, invitation links
and generated scene collections are gitignored. Send invitation links privately.
Both remote invitation links request local recording on the participant’s
computer. See [GUEST.md](GUEST.md) for the recording checklist.

## Import into OBS

Generate both local-host variants, then use **Scene Collection → Import** in
OBS to import both JSON files. Choose **WTF · Chirag local** or **WTF · Parth
local** from the Scene Collection menu. Both start on the duo.
The collection points at this checkout’s absolute asset paths, so keep the
folder in place and regenerate if you move it.

To configure the recording profile, quit OBS and run:

```bash
./apply_profile.sh
```

The helper backs up and updates the existing **Untitled** profile. If you use
another profile, set its path in the script first. It selects advanced output,
all six audio tracks, 1920 × 1080 at 30 fps, and 48 kHz audio. Encoder quality
still needs to be selected in OBS. Verify all six recording tracks are checked.

The redesign itself does not import a collection or modify your running OBS
configuration. Those installation steps are explicit.

## Recording tracks

| Track | Audio |
| --- | --- |
| 1 | Chirag voice, local or remote |
| 2 | Guest voice |
| 3 | Guest screen audio |
| 4 | Parth voice, local or remote |
| 5 | Remote cohost screen audio |
| 6 | Safety mix of all inputs |

Voice track numbers remain consistent when the local host changes. Track 5
contains the remote cohost’s screen audio, which can belong to either host.
Every scene references the local microphone and keeps the remote sources
active beneath the opaque backing, so switching to a screen or standby card
does not drop audio. The same underlying OBS source is reused across scenes.

After recording, with ffmpeg and ffprobe installed:

```bash
./verify_recording.sh recording.mkv
./verify_recording.sh --guest guest-episode.mkv
```

The duo check requires tracks 1, 4 and 6 to contain audio. `--guest` also
requires track 2. Silent optional guest or screen tracks are reported as idle.
Files with fewer than six tracks are rejected to avoid mislabeling stems.
This checks the resulting file; a short rehearsal is still needed to confirm
real microphones, remote feeds, lip sync and talkback on your hardware.

## Development and checks

```bash
python3 -m unittest test_scenes -v
npm ci
npm test
```

The Python suite checks scene geometry, source references, default duo and trio
behavior, native overlay sizes, audio routing, identity wiring and recording
verification logic. The browser suite tests the actual assets offline, query
overrides, transparency, motion, reduced motion, font loading and all twelve
preview scenes. It saves review screenshots under `render`.

Browser tests use Chrome or Brave when found in the standard macOS locations.
Set `CHROME` to another executable, or install the test browser with
`npx playwright install chromium`. Node 20 or later is required for these tests.

Shared styles and copy handling live in `assets/brand.css` and
`assets/brand.js`. The planet uses sphere and ring depth calculations, a
shared light direction and translucent rings. The standby signal follows a
12-second loop while the wordmark remains steady. Reduced-motion settings are
respected. Append `?t=3` to an asset URL to freeze motion for visual checks.

## License

Code is MIT licensed. Google Fonts retain their SIL Open Font License terms
in `assets/fonts`. Supplied brand artwork remains the property of its owners;
see [asset provenance](assets/README.md).
