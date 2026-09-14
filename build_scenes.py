#!/usr/bin/env python3
"""
Generate the OBS scene collection for "The Frontier Podcast".

Layout follows broadcast-news grammar rather than stream-overlay grammar:
a fixed top status strip, hard-edged camera cells in a middle band, and a
stacked lower block (hosts / headline / sponsors / ticker). Chrome is HTML
rendered by obs-browser; only the geometry lives here.

Schema mirrored from an OBS-written collection (format version 2) on
OBS 32.x / macOS, so field names match what OBS itself emits.

The remote guest arrives over VDO.Ninja (WebRTC) rather than by screen-capturing
a call window, so their camera and their screen share are two independently
addressable streams. See TRANSPORT below for the full signal path.

Usage:  VDO_ROOM=... VDO_GUEST_ID=... python3 build_scenes.py [-o OUTPUT.json]
"""

import argparse
import json
import os
import sys
import uuid
from urllib.parse import quote

CANVAS_W, CANVAS_H = 1920, 1080
COLLECTION_NAME = "Frontier Podcast"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Audio track bitmask: track N is bit (N-1).
TRACK_1, TRACK_2, TRACK_3, TRACK_6 = 1 << 0, 1 << 1, 1 << 2, 1 << 5

# --- TRANSPORT --------------------------------------------------------------
# Host  : joins https://vdo.ninja/?director=ROOM in Chrome, wearing headphones.
#         That tab is the *talkback* path -- it is how the guest hears the host,
#         and how the host hears the guest. OBS never plays guest audio out
#         (every source keeps monitoring_type 0); if it did, the host would hear
#         the guest twice at different latencies, which combs rather than adds.
#         The host's own voice is recorded from the local interface by MIC — Me,
#         not from the browser, so it stays uncompressed and ~0ms.
# Guest : opens the push link printed by --guest-link. That link also carries
#         &record, so their browser writes a pristine local copy to disk while
#         the compressed WebRTC feed drives these scenes. Clap at the top of the
#         episode; it is the sync point for swapping that file in during the edit.
# OBS   : receive-only. Two browser sources view the guest's two stream IDs.
VDO = "https://vdo.ninja/"

# OBS only activates a source's audio while the source is in the program scene
# AND visible. A hidden item is as silent as an absent one. So the guest feed is
# also placed in every scene as a full-canvas "carrier" at the very bottom of the
# z-order, completely covered by the opaque backing layer -- audibly present,
# visually absent. Without this the guest goes silent on every cut to a scene
# that has no guest cell (06 Screen Full, both cards), and because shutdown is
# off the page stays connected, so nothing looks wrong until the edit.
CARRIER = "carrier"   # stamped into private_settings so tests can tell them apart
SLOT = "slot"

# --- broadcast grid ---------------------------------------------------------
# The middle band is whatever the top strip and lower block do not occupy.
TOPBAR_H = 110
LOWER_H = 340
BAND_Y = TOPBAR_H + 8
BAND_H = CANVAS_H - LOWER_H - BAND_Y - 8      # 614
MARGIN, GAP, BORDER = 12, 8, 3

ASPECT = CANVAS_W / CANVAS_H


def pos_rel(x, y):
    """OBS normalized space: x spans [-16/9, +16/9], y spans [-1, +1].
    Verified against an OBS-written file: pos(0,0) -> (-1.7777778, -1.0)."""
    return {"x": (x / CANVAS_W) * 2 * ASPECT - ASPECT, "y": (y / CANVAS_H) * 2 - 1}


def size_rel(w, h):
    """Spans, so no origin offset."""
    return {"x": (w / CANVAS_W) * 2 * ASPECT, "y": (h / CANVAS_H) * 2}


def rgba(r, g, b, a=255):
    """OBS color sources store colour as a little-endian ABGR integer."""
    return (a << 24) | (b << 16) | (g << 8) | r


def asset_url(filename, **params):
    """file:// URL so query params work; is_local_file mode cannot carry them."""
    url = "file://" + quote(os.path.join(ASSETS, filename))
    if params:
        url += "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return url


def vdo_url(**params):
    """Build a vdo.ninja URL. A param whose value is True becomes a bare flag:
    the docs are explicit that "&solo takes no value", and writing solo=1 is not
    the same thing. Ordering is insertion order so the links stay readable."""
    parts = []
    for k, v in params.items():
        if v is True:
            parts.append(k)
        elif v not in (None, False):
            # ":" and "," are legal in a query value and vdo.ninja's stream
            # targeting is built out of them (ID:s for a share, "a,b" for two).
            parts.append(f"{k}={quote(str(v), safe=':,')}")
    return VDO + "?" + "&".join(parts)


def stream_id(raw):
    """Normalise a stream ID the way vdo.ninja itself does.

    From the docs: for &push and stream IDs, "non-alphanumeric characters are
    sanitized to _". The sanitising happens in the *guest's browser*, silently,
    after the page loads -- so a guest handed `guest-1234` publishes as
    `guest_1234` while OBS, which was never told, keeps subscribing to the
    hyphenated form. Nothing errors. OBS shows a video-shaped placeholder and
    the guest looks connected in the director tab, so the failure is invisible
    from both ends until you notice the feed is never actually them.

    This cost an hour of live debugging on 2026-09-14. Applying the same rule
    here, at the single point both the guest link and the OBS view URL are
    derived from, is what makes the two ends structurally incapable of
    disagreeing -- rather than relying on whoever picks the ID to remember.

    IDs are case sensitive, so case is deliberately preserved.
    """
    if not raw:
        raise ValueError("stream id must not be empty")
    out = "".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in raw)
    if len(out) > 64:                    # documented maximum
        raise ValueError(f"stream id too long ({len(out)} > 64): {out!r}")
    return out


def check_room(raw):
    """Rooms are documented as 1-49 *alphanumeric* characters. Unlike stream
    IDs, the docs do not say what happens to an illegal character -- it is
    simply unspecified. A hyphenated room happened to work in testing, but
    "worked once" is not a contract, and the identical assumption about stream
    IDs is exactly what broke. So this refuses rather than guesses: an
    unbuildable room is a ten-second fix, a silently mismatched one is not."""
    if not raw:
        raise ValueError("room must not be empty")
    if not (raw.isascii() and raw.isalnum()):
        raise ValueError(
            f"room {raw!r} contains non-alphanumeric characters. vdo.ninja "
            "documents rooms as alphanumeric only and does not define what "
            "happens otherwise. Use letters and digits, e.g. frontier9f3ab2c1.")
    if len(raw) > 49:                    # documented maximum
        raise ValueError(f"room too long ({len(raw)} > 49)")
    return raw


# Show palette, matched to the generated assets.
CYAN = rgba(0x35, 0xE0, 0xFF)
VOID = rgba(0x05, 0x06, 0x0D)


class Collection:
    def __init__(self):
        self.sources, self.by_name, self.scene_order = [], {}, []

    def source(self, sid, name, settings=None, mixers=0, muted=False,
               monitoring=0, sync=0):
        u = str(uuid.uuid4())
        self.sources.append({
            "prev_ver": 536870916, "name": name, "uuid": u,
            "id": sid, "versioned_id": sid, "settings": settings or {},
            "mixers": mixers, "sync": sync, "flags": 0,
            "volume": 1.0, "balance": 0.5, "enabled": True, "muted": muted,
            "push-to-mute": False, "push-to-mute-delay": 0,
            "push-to-talk": False, "push-to-talk-delay": 0,
            "hotkeys": {}, "deinterlace_mode": 0, "deinterlace_field_order": 0,
            "monitoring_type": monitoring, "private_settings": {},
        })
        self.by_name[name] = u
        return u

    def browser(self, name, filename, w, h, **params):
        """obs-browser renders offscreen at a fixed size, so w/h must match
        the asset's own pixel dimensions or it composites at the wrong scale."""
        return self.source("browser_source", name, {
            "url": asset_url(filename, **params),
            "width": w, "height": h,
            "reroute_audio": False,
            "restart_when_active": True,
            "shutdown": False,
            "webpage_control_level": 1,
        })

    def remote(self, name, url, audio_tracks=0, sync=0):
        """A WebRTC feed from vdo.ninja.

        Differs from browser() in three ways that all matter on air:
          * restart_when_active is OFF. On a local asset a reload is invisible;
            here it tears down and renegotiates the peer connection, so every
            cut into a scene holding this source would give seconds of black.
          * webpage_control_level drops to 0. There is no reason to hand a
            third-party origin read access to OBS state.
          * reroute_audio decides whether the stream's audio enters OBS at all.
            mixers is silently ignored unless it is on, so the two are set
            together or not at all.
        Rendered at full canvas: this feed is composited into boxes from 290px
        wide to full frame, so no single offscreen size is native everywhere.
        1080p downscales cleanly; anything smaller would upscale and blur."""
        return self.source("browser_source", name, {
            "url": url,
            "width": CANVAS_W, "height": CANVAS_H,
            "reroute_audio": bool(audio_tracks),
            "restart_when_active": False,
            "shutdown": False,
            "webpage_control_level": 0,
        }, mixers=audio_tracks, sync=sync)

    def item(self, name, x, y, w, h, fill=False, visible=True, role=None):
        """Lay out by bounds box. scale-inner fits and preserves aspect;
        scale-outer fills the box and crops the overflow.

        `role` is stamped into private_settings, which OBS round-trips without
        interpreting. It records *why* an item is there, so the geometry tests
        can tell a composited cell from an audio carrier instead of guessing
        from the source name."""
        return {
            "name": name, "source_uuid": self.by_name[name],
            "visible": visible, "locked": False, "rot": 0.0,
            "scale_ref": {"x": float(CANVAS_W), "y": float(CANVAS_H)},
            "align": 5,
            "bounds_type": 3 if fill else 2,
            "bounds_align": 0, "bounds_crop": False,
            "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0,
            "id": 0, "group_item_backup": False,
            "pos": {"x": float(x), "y": float(y)}, "pos_rel": pos_rel(x, y),
            "scale": {"x": 1.0, "y": 1.0}, "scale_rel": {"x": 1.0, "y": 1.0},
            "bounds": {"x": float(w), "y": float(h)}, "bounds_rel": size_rel(w, h),
            "scale_filter": "disable", "blend_method": "default",
            "blend_type": "normal",
            "show_transition": {"duration": 0}, "hide_transition": {"duration": 0},
            "private_settings": {"frontier_role": role} if role else {},
        }

    def cell(self, name, x, y, w, h):
        """A camera cell: accent border behind, feed cropped to fill on top.
        Returns items in top-first order for scene()."""
        return [
            self.item(name, x, y, w, h, fill=True),
            self.item("UI — Cell Border", x - BORDER, y - BORDER,
                      w + BORDER * 2, h + BORDER * 2),
        ]

    def carrier(self, name):
        """Keeps a source active so its audio keeps flowing. Full canvas and
        visible -- OBS deactivates hidden items -- but always the last entry in
        a top-first list, so it lands underneath the opaque backing."""
        return [self.item(name, 0, 0, CANVAS_W, CANVAS_H,
                          fill=True, role=CARRIER)]

    def scene(self, name, items, fkey=None, custom_size=False):
        """OBS stores items bottom-to-top; callers pass them top-first.

        fkey=None makes an un-hotkeyed scene that stays out of scene_order:
        used for SLOT — Content, which is a source container rather than
        something you ever cut to."""
        ordered = list(reversed(items))
        for i, it in enumerate(ordered, start=1):
            it["id"] = i
        u = str(uuid.uuid4())
        settings = {"id_counter": len(ordered), "custom_size": custom_size,
                    "items": ordered}
        if custom_size:
            settings["cx"], settings["cy"] = CANVAS_W, CANVAS_H
        self.sources.append({
            "prev_ver": 536870916, "name": name, "uuid": u,
            "id": "scene", "versioned_id": "scene",
            "settings": settings,
            "mixers": 0, "sync": 0, "flags": 0, "volume": 1.0, "balance": 0.5,
            "enabled": True, "muted": False,
            "push-to-mute": False, "push-to-mute-delay": 0,
            "push-to-talk": False, "push-to-talk-delay": 0,
            "hotkeys": {"OBSBasic.SelectScene": [{"key": fkey}]} if fkey else {},
            "deinterlace_mode": 0, "deinterlace_field_order": 0,
            "monitoring_type": 0, "private_settings": {},
        })
        self.by_name[name] = u
        if fkey:
            self.scene_order.append({"name": name})
        return u


def guest_link(room, guest_id, password=None, record_kbps=6000):
    """The link the guest opens. &record is a sender-side option: it writes a
    near-pristine local file on *their* machine, untouched by the network, which
    is the whole double-ender. The same guest_id must appear here as `push` and
    in the OBS source as `view`, or OBS renders an empty box forever.

    Both ends run the id through stream_id(), so the guest's browser has
    nothing left to sanitise and the two cannot drift apart."""
    return vdo_url(room=check_room(room), push=stream_id(guest_id),
                   password=password, record=record_kbps)


def build(room, guest_id, password=None):
    if not room or not guest_id:
        raise ValueError("room and guest_id are required")
    room, guest_id = check_room(room), stream_id(guest_id)
    c = Collection()

    # Show-level copy. These are the only strings an operator should need to
    # touch between episodes; every asset reads them off its URL query string,
    # so editing one here re-brands every scene at once.
    SHOW = "THE FRONTIER PODCAST"
    HOSTS = "CHIRAG PATIL @LORDPATIL  |  GUEST @HANDLE"
    HEADLINE = "EPISODE 01  //  THE FRONTIER PODCAST"   # the lower-third headline row
    TAGLINE = "SIGNALS, STORIES, AND THE PEOPLE BUILDING TOMORROW"
    PRESENTED_BY = "lordpatil.com"
    # lower_stack.html / outro_card.html split this on "|" and take the first 4.
    SPONSORS = "lordpatil.com|Dev Drink|Lord Socks|House of Lords"

    # --- capture sources: settings left empty so OBS opens Properties with
    # defaults. Encoding device IDs would hardcode absent hardware.
    c.source("macos-avcapture", "CAM — Me")
    c.source("screen_capture", "SCREEN — Share")

    c.source("coreaudio_input_capture", "MIC — Me", mixers=TRACK_1 | TRACK_6)

    # --- the remote guest, over WebRTC --------------------------------------
    # Two separate stream IDs, so camera and screen composite independently.
    # This is what the old window-capture approach could not do: if the guest
    # shared inside a call app, their face and their screen were the same
    # window, and the 3-column layout had nothing to put in two of its columns.
    view = dict(room=room, password=password, solo=True,
                cleanoutput=True, transparent=True)

    # Guest mic -> track 2. sync is left at 0 but exposed on purpose: WebRTC
    # adds 150-400ms that MIC — Me does not, so this is the dial to trim if the
    # guest sounds late in the mixed track.
    c.remote("CAM — Guest", vdo_url(view=guest_id, videobitrate=2500, **view),
             audio_tracks=TRACK_2 | TRACK_6, sync=0)

    # The share is addressed as "<id>:s" -- the default screensharetype=3 exposes
    # it under that suffix, so the guest needs no extra flags on their link.
    # Its audio is the guest's *system/tab* audio, not their voice, so it gets
    # its own track rather than being discarded: if they ever share a video,
    # track 3 is the only place that sound exists.
    c.remote("SCREEN — Guest Share",
             vdo_url(view=f"{guest_id}:s", videobitrate=3500, **view),
             audio_tracks=TRACK_3 | TRACK_6)

    # --- chrome ---
    c.browser("BG — Starfield", "starfield_bg.html", CANVAS_W, CANVAS_H)
    c.browser("UI — Top Bar", "topbar.html", CANVAS_W, TOPBAR_H,
              show=SHOW, presentedBy=PRESENTED_BY)
    # NB: lower_stack's "title" is the *headline* row, not the show name.
    c.browser("UI — Lower Stack", "lower_stack.html", CANVAS_W, LOWER_H,
              title=HEADLINE, hosts=HOSTS, sponsors=SPONSORS,
              presentedBy=PRESENTED_BY)
    c.browser("CARD — Title", "title_card.html", CANVAS_W, CANVAS_H,
              show=SHOW, tagline=TAGLINE, presentedBy=PRESENTED_BY)
    c.browser("CARD — Outro", "outro_card.html", CANVAS_W, CANVAS_H,
              show=SHOW, sponsors=SPONSORS, presentedBy=PRESENTED_BY)

    c.source("color_source_v3", "UI — Cell Border",
             {"color": CYAN, "width": CANVAS_W, "height": CANVAS_H})
    c.source("color_source_v3", "BG — Void",
             {"color": VOID, "width": CANVAS_W, "height": CANVAS_H})

    full = (0, 0, CANVAS_W, CANVAS_H)

    def chrome():
        """Persistent furniture, listed top-first, shared by every live scene."""
        return [
            c.item("UI — Top Bar", 0, 0, CANVAS_W, TOPBAR_H),
            c.item("UI — Lower Stack", 0, CANVAS_H - LOWER_H, CANVAS_W, LOWER_H),
        ]

    def backing():
        return [c.item("BG — Starfield", *full), c.item("BG — Void", *full)]

    def carriers():
        """Bottom of every scene, under the opaque backing. See CARRIER above:
        this is what stops the guest's audio from dropping out on a cut to a
        scene that has no guest cell."""
        return c.carrier("CAM — Guest") + c.carrier("SCREEN — Guest Share")

    def layers(*groups):
        """Top-first: content, then backing, then the silent audio carriers."""
        return [it for g in groups for it in g] + backing() + carriers()

    # One slot, two possible screens. Scenes 05/06/08 reference this nested
    # scene instead of a screen source directly, so switching between "my
    # screen" and "the guest's screen" is one visibility toggle in one place
    # rather than a parallel set of duplicated scenes and hotkeys. Toggling
    # inside the slot is also safe: it does not reload either page, whereas
    # duplicating the source across scenes would renegotiate the WebRTC
    # connection on every cut.
    c.scene("SLOT — Content", [
        c.item("SCREEN — Guest Share", *full, fill=True, visible=False, role=SLOT),
        c.item("SCREEN — Share", *full, fill=True, role=SLOT),
    ], custom_size=True)

    # --- geometry -----------------------------------------------------------
    # 2-up: two equal cells filling the band width.
    two_w = (CANVAS_W - MARGIN * 2 - GAP) // 2
    two_h = BAND_H
    two_y = BAND_Y

    # 3-column: centre content sized 16:9 to the band height, side rails split
    # the remainder. Keeps shared text large enough to actually read.
    ctr_h = BAND_H
    ctr_w = round(ctr_h * 16 / 9)
    rail_w = (CANVAS_W - MARGIN * 2 - GAP * 2 - ctr_w) // 2
    rail_h = round(rail_w * 9 / 16)
    rail_y = BAND_Y + (BAND_H - rail_h) // 2
    ctr_x = MARGIN + rail_w + GAP

    # Solo: one cell spanning the band.
    solo_w = CANVAS_W - MARGIN * 2

    # Over/under: stacked for vertical clips. The band only leaves ~303px per
    # cell, and a 16:9 cell that short would be 539px wide -- narrower than the
    # 607.5px 9:16 safe zone of a 1080-tall canvas, so a vertical crop would
    # slice both faces. Widen the cells past the safe zone instead and let
    # scale-outer crop the feed vertically; two wide strips stacked is the
    # standard shape for vertical podcast clips anyway.
    SAFE_9X16 = CANVAS_H * 9 / 16          # 607.5
    ou_h = (BAND_H - GAP) // 2
    ou_w = round(SAFE_9X16) + 32           # margin past the safe zone
    ou_x = (CANVAS_W - ou_w) // 2

    c.scene("01 Intro", layers([c.item("CARD — Title", *full)]), "OBS_KEY_F1")

    c.scene("02 Solo — Me",
            layers(chrome(), c.cell("CAM — Me", MARGIN, BAND_Y, solo_w, BAND_H)),
            "OBS_KEY_F2")

    c.scene("03 Solo — Guest",
            layers(chrome(),
                   c.cell("CAM — Guest", MARGIN, BAND_Y, solo_w, BAND_H)),
            "OBS_KEY_F3")

    c.scene("04 Two Shot",
            layers(chrome(),
                   c.cell("CAM — Me", MARGIN, two_y, two_w, two_h),
                   c.cell("CAM — Guest",
                          MARGIN + two_w + GAP, two_y, two_w, two_h)),
            "OBS_KEY_F4")

    # Guest left, content centre, host right — the layout that keeps shared
    # text readable, unlike a corner picture-in-picture. The centre is the
    # content slot, so it shows whichever screen is live in SLOT — Content.
    c.scene("05 Screen — 3 Column",
            layers(chrome(),
                   c.cell("CAM — Guest", MARGIN, rail_y, rail_w, rail_h),
                   c.cell("SLOT — Content", ctr_x, BAND_Y, ctr_w, ctr_h),
                   c.cell("CAM — Me", ctr_x + ctr_w + GAP, rail_y, rail_w, rail_h)),
            "OBS_KEY_F5")

    c.scene("06 Screen Full",
            layers(chrome(),
                   c.cell("SLOT — Content", MARGIN, BAND_Y, solo_w, BAND_H)),
            "OBS_KEY_F6")

    # Screen plus guest only: for when the guest is driving the demo.
    scr_w = CANVAS_W - MARGIN * 2 - GAP - rail_w
    c.scene("08 Screen + Guest",
            layers(chrome(),
                   c.cell("SLOT — Content", MARGIN, BAND_Y, scr_w, BAND_H),
                   c.cell("CAM — Guest",
                          MARGIN + scr_w + GAP, rail_y, rail_w, rail_h)),
            "OBS_KEY_F8")

    c.scene("09 Two Shot — Over/Under",
            layers(chrome(),
                   c.cell("CAM — Me", ou_x, BAND_Y, ou_w, ou_h),
                   c.cell("CAM — Guest", ou_x, BAND_Y + ou_h + GAP, ou_w, ou_h)),
            "OBS_KEY_F9")

    c.scene("10 Outro", layers([c.item("CARD — Outro", *full)]), "OBS_KEY_F10")

    first = c.scene_order[0]["name"]
    return {
        "name": COLLECTION_NAME,
        "current_scene": first, "current_program_scene": first,
        "current_transition": "Fade", "transition_duration": 300,
        "transitions": [], "quick_transitions": [],
        "scene_order": c.scene_order, "sources": c.sources,
        "groups": [], "canvases": [], "saved_projectors": [], "modules": {},
        "preview_locked": False, "scaling_enabled": False, "scaling_level": 0,
        "scaling_off_x": 0.0, "scaling_off_y": 0.0,
        "virtual-camera": {"type2": 3},
        "resolution": {"x": CANVAS_W, "y": CANVAS_H},
        "version": 2,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Generate the Frontier Podcast OBS scene collection.")
    ap.add_argument("-o", "--output", default="podcast_scenes.json")
    ap.add_argument("--guest-link", action="store_true",
                    help="print the link to send the guest, and exit")
    args = ap.parse_args()

    # Deliberately no defaults. A vdo.ninja room is unauthenticated: anyone who
    # knows the name can walk into the recording. A placeholder default would
    # let a typo'd or unset variable produce a *successful* build pointing at a
    # real, guessable, public room -- a silent misconfiguration that is far
    # worse than a crash. So: fail loudly instead.
    room = os.environ.get("VDO_ROOM")
    guest = os.environ.get("VDO_GUEST_ID")
    password = os.environ.get("VDO_PASSWORD")     # optional but strongly advised
    missing = [n for n, v in (("VDO_ROOM", room), ("VDO_GUEST_ID", guest)) if not v]
    if missing:
        sys.exit(
            f"error: {' and '.join(missing)} not set.\n"
            "  These identify your private vdo.ninja room and must not be\n"
            "  committed, so they are read from the environment:\n\n"
            # No hyphens: vdo.ninja rewrites them to _ inside a stream id and
            # leaves rooms undefined. stream_id()/check_room() enforce this,
            # but generating clean values means never hitting either.
            "    export VDO_ROOM=frontier$(openssl rand -hex 4)\n"
            "    export VDO_GUEST_ID=guest$(openssl rand -hex 4)\n"
            "    export VDO_PASSWORD=$(openssl rand -hex 12)   # optional\n")

    if args.guest_link:
        print(guest_link(room, guest, password))
        sys.exit(0)

    with open(args.output, "w") as f:
        json.dump(build(room, guest, password), f, indent=4)
    # The written JSON contains the resolved room URLs in plaintext. It is a
    # secret artifact in the same way the env vars are; do not commit it.
    print(f"wrote {args.output}")
