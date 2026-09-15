#!/usr/bin/env python3
"""
Generate the OBS scene collection for "What's the Frontier".

Chirag and Parth are the default duo, with a separate optional guest feed.
HTML overlays share the WTF typography, palette and supplied brand artwork.
The geometry and six-track audio routing live here.

Schema mirrored from an OBS-written collection (format version 2) on
OBS 32.x / macOS, so field names match what OBS itself emits.

The remote guest arrives over VDO.Ninja (WebRTC) rather than by screen-capturing
a call window, so their camera and their screen share are two independently
addressable streams. See TRANSPORT below for the full signal path.

Usage: set VDO_ROOM and participant IDs, then use --both-local-hosts to
generate both collection choices for OBS, or --local-host for one variant.
"""

import argparse
import json
import os
import uuid
from pathlib import Path
from urllib.parse import quote

CANVAS_W, CANVAS_H = 1920, 1080
COLLECTION_NAME = "WTF"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Audio track bitmask: track N is bit (N-1).
TRACK_1, TRACK_2, TRACK_3, TRACK_6 = 1 << 0, 1 << 1, 1 << 2, 1 << 5
TRACK_4, TRACK_5 = 1 << 3, 1 << 4

# --- TRANSPORT --------------------------------------------------------------
# Local : the selected host joins the room's director tab wearing headphones.
#         That tab is the *talkback* path -- it is how the guest hears the host,
#         and how the host hears the guest. OBS never plays guest audio out
#         (every source keeps monitoring_type 0); if it did, the host would hear
#         the guest twice at different latencies, which combs rather than adds.
#         The host's own voice is recorded from the local interface by MIC,
#         not from the browser, so it stays uncompressed and ~0ms.
# Guest : opens the push link printed by --guest-link. That link also carries
#         &record, so their browser writes a pristine local copy to disk while
#         the compressed WebRTC feed drives these scenes. Clap at the top of the
#         episode; it is the sync point for swapping that file in during the edit.
# Cohost: opens --parth-link or --chirag-link, depending on who is remote.
# OBS   : receive-only. Four browser sources receive the two remote people.
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
TOPBAR_H = 96
LOWER_H = 196
BAND_Y = TOPBAR_H + 16
BAND_H = CANVAS_H - LOWER_H - BAND_Y - 16
MARGIN, GAP, BORDER = 48, 24, 2

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
SPECTRAL = rgba(0x8B, 0x7C, 0xFF)
VOID = rgba(0x07, 0x08, 0x0D)


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

    def browser(self, source_name, filename, w, h, **params):
        """obs-browser renders offscreen at a fixed size, so w/h must match
        the asset's own pixel dimensions or it composites at the wrong scale."""
        return self.source("browser_source", source_name, {
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

    def cell(self, name, x, y, w, h, fill=True):
        """A camera cell: accent border behind, feed cropped to fill on top.
        Returns items in top-first order for scene()."""
        return [
            self.item(name, x, y, w, h, fill=fill),
            self.item("UI · Cell Border", x - BORDER, y - BORDER,
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
        used for SLOT · Content, which is a source container rather than
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


def build(room, guest_id, password=None, *, parth_id=None, chirag_id=None,
          local_host="chirag",
          episode="01", title="Conversations at the edge of possible",
          guest_name="Guest", guest_role="In conversation"):
    if local_host not in ("chirag", "parth"):
        raise ValueError("local_host must be chirag or parth")
    remote_host = "parth" if local_host == "chirag" else "chirag"
    host_ids = {"chirag": chirag_id, "parth": parth_id}
    if not room or not guest_id or not host_ids[remote_host]:
        raise ValueError(f"room, guest_id and {remote_host}_id are required")
    room = check_room(room)
    guest_id = stream_id(guest_id)
    host_ids = {name: stream_id(value) for name, value in host_ids.items() if value}
    ids = [guest_id, *host_ids.values()]
    if len(set(ids)) != len(ids):
        raise ValueError("Chirag, Parth and the guest need distinct stream IDs")
    local_name, remote_name = local_host.title(), remote_host.title()
    voice_tracks = {"chirag": TRACK_1, "parth": TRACK_4}
    c = Collection()

    show = "what’s the frontier"
    hosts = "Chirag & Parth"
    common = dict(show=show, episode=episode)
    identity = dict(hosts=hosts, chiragSite="lordpatil.com",
                    parthSite="parthshastri.co.in")
    c.source("macos-avcapture", f"CAM · {local_name}")
    c.source("screen_capture", "SCREEN · Share")
    c.source("coreaudio_input_capture", f"MIC · {local_name}",
             mixers=voice_tracks[local_host] | TRACK_6)

    # The selected host operates the local studio. Voice track numbers stay
    # attached to the people, even when local and remote capture swap roles.
    view = dict(room=room, password=password, solo=True,
                cleanoutput=True, transparent=True)
    for person, sid, voice, share in (
        (remote_name, host_ids[remote_host], voice_tracks[remote_host], TRACK_5),
        ("Guest", guest_id, TRACK_2, TRACK_3),
    ):
        c.remote(f"CAM · {person}",
                 vdo_url(view=sid, videobitrate=2500, **view),
                 audio_tracks=voice | TRACK_6)
        c.remote(f"SCREEN · {person} Share",
                 vdo_url(view=f"{sid}:s", videobitrate=3500, **view),
                 audio_tracks=share | TRACK_6)

    c.browser("BG · Starfield", "starfield_bg.html", CANVAS_W, CANVAS_H)
    c.browser("UI · Top Bar", "topbar.html", CANVAS_W, TOPBAR_H, **common)
    c.browser("UI · Lower Stack", "lower_stack.html", CANVAS_W, LOWER_H,
              title=title, **identity, episode=episode)
    c.browser("CARD · Title", "title_card.html", CANVAS_W, CANVAS_H,
              status="Starting soon", **common, **identity)
    c.browser("CARD · Break", "title_card.html", CANVAS_W, CANVAS_H,
              status="Back shortly", **common, **identity)
    c.browser("CARD · Outro", "outro_card.html", CANVAS_W, CANVAS_H,
              thanks="Stay curious.", **common,
              chiragSite=identity["chiragSite"], parthSite=identity["parthSite"])
    c.source("color_source_v3", "UI · Cell Border",
             {"color": SPECTRAL, "width": CANVAS_W, "height": CANVAS_H})
    c.source("color_source_v3", "BG · Void",
             {"color": VOID, "width": CANVAS_W, "height": CANVAS_H})

    full = (0, 0, CANVAS_W, CANVAS_H)

    def chrome():
        return [
            c.item("UI · Top Bar", 0, 0, CANVAS_W, TOPBAR_H),
            c.item("UI · Lower Stack", 0, CANVAS_H - LOWER_H, CANVAS_W, LOWER_H),
        ]

    def layers(*groups):
        items = [it for group in groups for it in group]
        items += [c.item("BG · Starfield", *full), c.item("BG · Void", *full)]
        # Local mic must also be referenced by each scene. Sources that only
        # exist in the collection are not automatically global audio devices.
        for name in (f"MIC · {local_name}", f"CAM · {remote_name}",
                     f"SCREEN · {remote_name} Share",
                     "CAM · Guest", "SCREEN · Guest Share"):
            items += c.carrier(name)
        return items

    people = {
        "Chirag": ("Chirag", "Co-host", "lordpatil.com"),
        "Parth": ("Parth", "Co-host", "parthshastri.co.in"),
        "Guest": (guest_name, guest_role, ""),
    }

    def camera(person, x, y, w, h):
        # Each browser label is rendered at its composited size so smaller
        # screen-sharing rails do not shrink or blur the names.
        lw, lh = min(w - 32, 560), 64
        label = f"UI · {person} Label {lw}"
        if label not in c.by_name:
            name, role, website = people[person]
            c.browser(label, "participant_label.html", lw, lh,
                      name=name, role=role, website=website, person=person.lower())
        return [c.item(label, x + 16, y + h - lh - 16, lw, lh)] + c.cell(
            f"CAM · {person}", x, y, w, h)

    # One source slot for the operator, cohost or guest screen. Only one item
    # is visible by default. Switching this slot does not reconnect WebRTC.
    c.scene("SLOT · Content", [
        c.item("SCREEN · Guest Share", *full, visible=False, role=SLOT),
        c.item(f"SCREEN · {remote_name} Share", *full, visible=False, role=SLOT),
        c.item("SCREEN · Share", *full, role=SLOT),
    ], custom_size=True)

    width = CANVAS_W - MARGIN * 2
    duo_w = (width - GAP) // 2
    trio_w = (width - GAP * 2) // 3

    def duo():
        return (camera("Chirag", MARGIN, BAND_Y, duo_w, BAND_H) +
                camera("Parth", MARGIN + duo_w + GAP, BAND_Y, duo_w, BAND_H))

    def screen_with_people(names):
        # Keep the 16:9 share centred and dominant. Participants sit in small
        # corner cards outside it, so slide text is never covered or cropped.
        content_w = 1280
        content_h = 720
        content_x = (CANVAS_W - content_w) // 2
        content_y = BAND_Y + (BAND_H - content_h) // 2
        card_w = content_x - MARGIN - GAP
        card_h = 200
        left_x = MARGIN
        right_x = CANVAS_W - MARGIN - card_w
        top_y = BAND_Y
        bottom_y = BAND_Y + BAND_H - card_h
        corners = ((left_x, bottom_y), (right_x, bottom_y),
                   (left_x, top_y), (right_x, top_y))
        items = c.cell("SLOT · Content", content_x, content_y,
                       content_w, content_h, fill=False)
        for name, (x, y) in zip(names, corners):
            items += camera(name, x, y, card_w, card_h)
        return items

    c.scene("01 Standby", layers([c.item("CARD · Title", *full)]), "OBS_KEY_F1")
    c.scene("02 Solo · Chirag",
            layers(chrome(), camera("Chirag", MARGIN, BAND_Y, width, BAND_H)),
            "OBS_KEY_F2")
    c.scene("03 Solo · Parth",
            layers(chrome(), camera("Parth", MARGIN, BAND_Y, width, BAND_H)),
            "OBS_KEY_F3")
    c.scene("04 Duo", layers(chrome(), duo()), "OBS_KEY_F4")
    c.scene("05 Screen · Duo",
            layers(chrome(), screen_with_people(["Chirag", "Parth"])),
            "OBS_KEY_F5")
    c.scene("06 Screen Full",
            layers(chrome(), c.cell("SLOT · Content", MARGIN, BAND_Y,
                                   width, BAND_H, fill=False)), "OBS_KEY_F6")
    trio = []
    for index, name in enumerate(("Chirag", "Guest", "Parth")):
        trio += camera(name, MARGIN + index * (trio_w + GAP), BAND_Y,
                       trio_w, BAND_H)
    c.scene("07 Trio · With Guest", layers(chrome(), trio), "OBS_KEY_F7")
    c.scene("08 Screen · Trio",
            layers(chrome(), screen_with_people(["Chirag", "Parth", "Guest"])),
            "OBS_KEY_F8")
    ou_h = (BAND_H - GAP) // 2
    ou_w = round(CANVAS_H * 9 / 16) + 32
    ou_x = (CANVAS_W - ou_w) // 2
    c.scene("09 Duo · Vertical", layers(
        chrome(), camera("Chirag", ou_x, BAND_Y, ou_w, ou_h),
        camera("Parth", ou_x, BAND_Y + ou_h + GAP, ou_w, ou_h)),
        "OBS_KEY_F9")
    c.scene("10 Outro", layers([c.item("CARD · Outro", *full)]), "OBS_KEY_F10")
    c.scene("11 Solo · Guest",
            layers(chrome(), camera("Guest", MARGIN, BAND_Y, width, BAND_H)),
            "OBS_KEY_F11")
    c.scene("12 Break", layers([c.item("CARD · Break", *full)]), "OBS_KEY_F12")

    return {
        "name": f"{COLLECTION_NAME} · {local_name} local",
        "current_scene": "04 Duo", "current_program_scene": "04 Duo",
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
    ap = argparse.ArgumentParser(description="Generate the WTF duo podcast studio.")
    ap.add_argument("-o", "--output", default="podcast_scenes.json")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--local-host", choices=("chirag", "parth"), default="chirag",
                       help="choose whose camera and microphone are local")
    modes.add_argument("--both-local-hosts", action="store_true",
                       help="generate both collections for selection in OBS")
    links = ap.add_mutually_exclusive_group()
    links.add_argument("--guest-link", action="store_true", help="print the guest invitation")
    links.add_argument("--parth-link", action="store_true", help="print Parth's invitation")
    links.add_argument("--chirag-link", action="store_true", help="print Chirag's invitation")
    ap.add_argument("--episode", default="01")
    ap.add_argument("--title", default="Conversations at the edge of possible")
    ap.add_argument("--guest-name", default="Guest")
    ap.add_argument("--guest-role", default="In conversation")
    args = ap.parse_args()
    room = os.environ.get("VDO_ROOM")
    guest = os.environ.get("VDO_GUEST_ID")
    parth = os.environ.get("VDO_PARTH_ID")
    chirag = os.environ.get("VDO_CHIRAG_ID")
    password = os.environ.get("VDO_PASSWORD")
    required = [("VDO_ROOM", room)]
    invitation = ("guest" if args.guest_link else "parth" if args.parth_link
                  else "chirag" if args.chirag_link else None)
    if invitation and args.both_local_hosts:
        ap.error("generate collections or print an invitation in separate commands")
    ids = {"guest": guest, "parth": parth, "chirag": chirag}
    local_hosts = ("chirag", "parth") if args.both_local_hosts else (args.local_host,)
    needed = [invitation] if invitation else [
        "guest", *("parth" if host == "chirag" else "chirag" for host in local_hosts)]
    required.extend((f"VDO_{person.upper()}_ID", ids[person]) for person in needed)
    missing = [name for name, value in required if not value]
    if missing:
        ap.error(f"{', '.join(missing)} not set. See .env.example for setup.")
    try:
        if invitation:
            print(guest_link(room, ids[invitation], password))
        else:
            # Validate both variants before writing either file.
            collections = [(host, build(
                room, guest, password, parth_id=parth, chirag_id=chirag,
                local_host=host, episode=args.episode, title=args.title,
                guest_name=args.guest_name, guest_role=args.guest_role))
                for host in local_hosts]
            output = Path(args.output)
            for host, result in collections:
                target = output.with_name(f"{output.stem}_{host}_local{output.suffix}") \
                    if args.both_local_hosts else output
                with target.open("w") as f:
                    json.dump(result, f, indent=4)
                print(f"wrote {target} ({result['name']})")
    except ValueError as exc:
        ap.error(str(exc))
