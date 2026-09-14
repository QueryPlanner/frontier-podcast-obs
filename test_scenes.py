#!/usr/bin/env python3
"""
Tests for the WTF OBS collection, geometry, identity wiring and audio routing.
Browser rendering is verified separately by test_render.cjs.

Run:  python3 test_scenes.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlparse, parse_qs, unquote

import build_scenes as bs
from build_scenes import (
    CANVAS_W, CANVAS_H, TOPBAR_H, LOWER_H, BAND_Y, BAND_H,
    MARGIN, GAP, BORDER, CARRIER, build, guest_link, stream_id, check_room,
)

# Fixtures, not real credentials. build() takes these as arguments precisely so
# the tests never depend on the operator's actual room being in the environment.
# Alphanumeric on purpose: these used to be "test-room"/"test-guest", which is
# the very shape vdo.ninja silently rewrites. See TestIdentifierSanitising.
ROOM, GUEST_ID, PASSWORD = "testroom", "testguest", "test-pw"
PARTH_ID = "testparth"

# Cells that hold a live video feed. Chrome (top bar, lower stack, cards) and
# the full-canvas backing layers are deliberately allowed outside the band.
# SLOT · Content is a nested scene, but it is composited exactly like a feed.
FEEDS = {"CAM · Chirag", "CAM · Parth", "CAM · Guest", "SLOT · Content"}
BAND_ITEMS = FEEDS | {"UI · Cell Border"}

# Browser sources whose URL is a remote WebRTC feed rather than a local asset.
REMOTE = {"CAM · Guest", "SCREEN · Guest Share", "CAM · Parth", "SCREEN · Parth Share"}

# The slot is a source container, never something you cut to, so it is exempt
# from the layout rules that govern on-air scenes.
SLOT_SCENE = "SLOT · Content"


def collection():
    return build(ROOM, GUEST_ID, PASSWORD, parth_id=PARTH_ID)


def scenes(col):
    """On-air scenes only. Excludes the slot container."""
    return [s for s in col["sources"]
            if s["id"] == "scene" and s["name"] != SLOT_SCENE]


def cells(scene):
    """Composited feed items: excludes the invisible audio carriers, which are
    full-canvas by design and would otherwise trip every geometry rule."""
    return [it for it in scene["settings"]["items"]
            if it["name"] in FEEDS
            and it["private_settings"].get("frontier_role") != CARRIER]


def sources_by_name(col):
    return {s["name"]: s for s in col["sources"]}


def box(item):
    """Absolute pixel box (x0, y0, x1, y1) of a scene item's bounds."""
    x, y = item["pos"]["x"], item["pos"]["y"]
    w, h = item["bounds"]["x"], item["bounds"]["y"]
    return x, y, x + w, y + h


class TestGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.col = collection()
        cls.scenes = scenes(cls.col)

    def test_band_arithmetic(self):
        """The middle band must not collide with the top strip or lower block."""
        self.assertEqual(BAND_Y, TOPBAR_H + 16)
        self.assertEqual(BAND_H, 756)
        self.assertEqual(BAND_Y + BAND_H, CANVAS_H - LOWER_H - 16)

    def test_every_item_inside_canvas(self):
        for sc in self.scenes:
            for it in sc["settings"]["items"]:
                x0, y0, x1, y1 = box(it)
                self.assertGreaterEqual(x0, 0, f'{sc["name"]}/{it["name"]} off left')
                self.assertGreaterEqual(y0, 0, f'{sc["name"]}/{it["name"]} off top')
                self.assertLessEqual(x1, CANVAS_W, f'{sc["name"]}/{it["name"]} off right')
                self.assertLessEqual(y1, CANVAS_H, f'{sc["name"]}/{it["name"]} off bottom')

    def test_feeds_and_borders_stay_in_band(self):
        """A cell border is drawn 3px outside its feed; even that must clear
        the top strip and the lower block, or the chrome gets overlapped."""
        for sc in self.scenes:
            for it in sc["settings"]["items"]:
                if it["name"] not in BAND_ITEMS:
                    continue
                if it["private_settings"].get("frontier_role") == CARRIER:
                    continue     # full-canvas and hidden under the backing
                _, y0, _, y1 = box(it)
                self.assertGreaterEqual(
                    y0, TOPBAR_H, f'{sc["name"]}/{it["name"]} intrudes into top bar')
                self.assertLessEqual(
                    y1, CANVAS_H - LOWER_H,
                    f'{sc["name"]}/{it["name"]} intrudes into lower stack')

    def test_pos_rel_round_trips(self):
        """pos_rel/bounds_rel are what OBS actually reads on a multi-canvas
        build; if they disagree with pos/bounds the layout silently shifts."""
        for sc in self.scenes:
            for it in sc["settings"]["items"]:
                px, py = it["pos"]["x"], it["pos"]["y"]
                self.assertAlmostEqual(it["pos_rel"]["x"], bs.pos_rel(px, py)["x"], places=9)
                self.assertAlmostEqual(it["pos_rel"]["y"], bs.pos_rel(px, py)["y"], places=9)
                bw, bh = it["bounds"]["x"], it["bounds"]["y"]
                self.assertAlmostEqual(it["bounds_rel"]["x"], bs.size_rel(bw, bh)["x"], places=9)
                self.assertAlmostEqual(it["bounds_rel"]["y"], bs.size_rel(bw, bh)["y"], places=9)

    def test_pos_rel_origin_matches_obs(self):
        """Anchor: verified against a collection OBS itself wrote."""
        self.assertAlmostEqual(bs.pos_rel(0, 0)["x"], -16 / 9, places=6)
        self.assertAlmostEqual(bs.pos_rel(0, 0)["y"], -1.0, places=6)
        self.assertAlmostEqual(bs.pos_rel(CANVAS_W, CANVAS_H)["x"], 16 / 9, places=6)
        self.assertAlmostEqual(bs.pos_rel(CANVAS_W, CANVAS_H)["y"], 1.0, places=6)

    def test_border_sits_behind_its_feed(self):
        """Items are stored bottom-to-top, so the border must come first in the
        list. If this inverts, the cyan rect covers the face."""
        for sc in self.scenes:
            items = sc["settings"]["items"]
            names = [it["name"] for it in items]
            cell_ids = {id(it) for it in cells(sc)}
            for i, (n, it) in enumerate(zip(names, items)):
                if id(it) in cell_ids:
                    borders_below = [j for j, m in enumerate(names)
                                     if m == "UI · Cell Border" and j < i]
                    self.assertTrue(
                        borders_below,
                        f'{sc["name"]}: feed {n} has no border beneath it')

    def test_border_is_three_px_larger_than_feed(self):
        for sc in self.scenes:
            items = sc["settings"]["items"]
            feeds = cells(sc)
            borders = [it for it in items if it["name"] == "UI · Cell Border"]
            self.assertEqual(len(feeds), len(borders), sc["name"])
            for f in feeds:
                fx0, fy0, fx1, fy1 = box(f)
                match = [b for b in borders
                         if box(b) == (fx0 - BORDER, fy0 - BORDER,
                                       fx1 + BORDER, fy1 + BORDER)]
                self.assertTrue(match, f'{sc["name"]}: no matching border for {f["name"]}')

    def test_feeds_fill_and_chrome_fits(self):
        """Feeds use scale-outer (3) so they fill the cell and crop; chrome and
        cards use scale-inner (2) so nothing is cropped off a 1:1 asset.
        Carriers fill too -- they are covered, but a letterboxed carrier would
        be a sign the item was not laid out as intended."""
        for sc in self.scenes:
            for it in sc["settings"]["items"]:
                live = (it["name"] in FEEDS - {"SLOT · Content"}
                        or it["private_settings"].get("frontier_role") == CARRIER)
                want = 3 if live else 2
                self.assertEqual(it["bounds_type"], want,
                                 f'{sc["name"]}/{it["name"]} wrong bounds_type')

    def test_cells_do_not_overlap_each_other(self):
        """Two feeds overlapping means one is hidden behind the other."""
        for sc in self.scenes:
            feeds = cells(sc)
            for i in range(len(feeds)):
                for j in range(i + 1, len(feeds)):
                    ax0, ay0, ax1, ay1 = box(feeds[i])
                    bx0, by0, bx1, by1 = box(feeds[j])
                    overlap = not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)
                    self.assertFalse(
                        overlap,
                        f'{sc["name"]}: {feeds[i]["name"]} overlaps {feeds[j]["name"]}')

    def test_over_under_covers_9x16_safe_zone(self):
        """A vertical clip crops the 1080-tall canvas to 607.5px wide, centred.
        Both stacked cells must span that whole window or faces get sliced."""
        safe = CANVAS_H * 9 / 16
        lo, hi = (CANVAS_W - safe) / 2, (CANVAS_W + safe) / 2
        sc = next(s for s in self.scenes if s["name"] == "09 Duo · Vertical")
        feeds = cells(sc)
        self.assertEqual(len(feeds), 2)
        for f in feeds:
            x0, _, x1, _ = box(f)
            self.assertLessEqual(x0, lo, f'{f["name"]} left edge {x0} inside safe zone {lo}')
            self.assertGreaterEqual(x1, hi, f'{f["name"]} right edge {x1} inside safe zone {hi}')

    def test_three_column_keeps_content_largest(self):
        """The point of the 3-column layout is that shared content stays big.
        If a side rail ever gets wider than the centre, the layout has drifted."""
        sc = next(s for s in self.scenes if s["name"] == "05 Screen · Duo")
        by_name = {}
        for it in cells(sc):
            by_name.setdefault(it["name"], []).append(box(it))
        screen = by_name["SLOT · Content"][0]
        screen_w = screen[2] - screen[0]
        for rail in ("CAM · Chirag", "CAM · Parth"):
            rw = by_name[rail][0][2] - by_name[rail][0][0]
            self.assertGreater(screen_w, rw * 2,
                               "centre content should dominate the side rails")


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.col = collection()
        cls.by_name = sources_by_name(cls.col)
        cls.scenes = scenes(cls.col)

    def test_audio_track_routing(self):
        """Track 1 = my mic, 2 = the guest's voice, 3 = audio from whatever the
        guest shares, 6 = a safety mix of all of them. Separate tracks are what
        make the recording fixable in post."""
        self.assertEqual(self.by_name["MIC · Chirag"]["mixers"], 0b100001)           # 33
        self.assertEqual(self.by_name["CAM · Guest"]["mixers"], 0b100010)        # 34
        self.assertEqual(self.by_name["SCREEN · Guest Share"]["mixers"], 0b100100)  # 36
        self.assertEqual(self.by_name["CAM · Parth"]["mixers"], 0b101000)
        self.assertEqual(self.by_name["SCREEN · Parth Share"]["mixers"], 0b110000)

    def test_no_two_sources_claim_the_same_isolated_track(self):
        """The point of isolated tracks is that each holds exactly one voice.
        Two sources sharing track 2 would mix them together permanently, which
        no amount of editing can undo."""
        for track in range(5):
            claimants = [s["name"] for s in self.col["sources"]
                         if s["mixers"] & (1 << track)]
            self.assertLessEqual(len(claimants), 1,
                                 f"track {track + 1} claimed by {claimants}")

    def test_monitoring_is_off_everywhere(self):
        """Deliberate, and the opposite of what you would guess. The host hears
        the guest in the vdo.ninja director tab, not from OBS. If OBS also
        monitored, the host would hear the guest twice a few hundred ms apart,
        which combs rather than adds. Turning monitoring on here is a real
        change to the audio design, not a convenience toggle."""
        for s in self.col["sources"]:
            self.assertEqual(s["monitoring_type"], 0, s["name"])

    def test_every_item_references_a_real_source(self):
        uuids = {s["uuid"] for s in self.col["sources"]}
        for sc in self.scenes:
            for it in sc["settings"]["items"]:
                self.assertIn(it["source_uuid"], uuids,
                              f'{sc["name"]}/{it["name"]} dangling source_uuid')
                self.assertEqual(it["source_uuid"], self.by_name[it["name"]]["uuid"])

    def test_uuids_unique(self):
        uuids = [s["uuid"] for s in self.col["sources"]]
        self.assertEqual(len(uuids), len(set(uuids)))

    def test_item_ids_sequential_per_scene(self):
        for sc in self.scenes:
            items = sc["settings"]["items"]
            self.assertEqual([it["id"] for it in items], list(range(1, len(items) + 1)))
            self.assertEqual(sc["settings"]["id_counter"], len(items))

    def test_hotkeys_unique(self):
        keys = [sc["hotkeys"]["OBSBasic.SelectScene"][0]["key"] for sc in self.scenes]
        self.assertEqual(len(keys), len(set(keys)), "two scenes share a hotkey")

    def test_scene_order_is_alphanumeric(self):
        """Scene names are number-prefixed so the sidebar order matches the
        hotkey order. A rename that breaks this makes F-keys unpredictable."""
        names = [s["name"] for s in self.col["scene_order"]]
        self.assertEqual(names, sorted(names))

    def test_scene_order_matches_hotkey_order(self):
        order = [s["name"] for s in self.col["scene_order"]]
        by_scene = {sc["name"]: sc["hotkeys"]["OBSBasic.SelectScene"][0]["key"]
                    for sc in self.scenes}
        nums = [int(by_scene[n].removeprefix("OBS_KEY_F")) for n in order]
        self.assertEqual(nums, sorted(nums))

    def test_collection_header(self):
        self.assertEqual(self.col["version"], 2)
        self.assertEqual(self.col["resolution"], {"x": CANVAS_W, "y": CANVAS_H})
        self.assertIn(self.col["current_program_scene"],
                      [s["name"] for s in self.scenes])

    def test_live_scenes_all_carry_chrome(self):
        """Every scene except the two full-screen cards must show the top bar
        and lower stack, or the branding flickers on switch."""
        for sc in self.scenes:
            names = {it["name"] for it in sc["settings"]["items"]}
            if names & {"CARD · Title", "CARD · Outro", "CARD · Break"}:
                continue
            self.assertIn("UI · Top Bar", names, sc["name"])
            self.assertIn("UI · Lower Stack", names, sc["name"])

    def test_serializes_to_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out.json")
            with open(p, "w") as f:
                json.dump(self.col, f, indent=4)
            with open(p) as f:
                self.assertEqual(json.load(f)["name"], self.col["name"])


class TestAssetWiring(unittest.TestCase):
    """The assets read their copy off the URL query string. These tests pin the
    contract between build_scenes.py and the HTML, which has already drifted
    once (the headline slot was being fed the show name)."""

    @classmethod
    def setUpClass(cls):
        cls.col = collection()
        cls.browsers = {s["name"]: s for s in cls.col["sources"]
                        if s["id"] == "browser_source" and s["name"] not in REMOTE}

    def params(self, name):
        return parse_qs(urlparse(self.browsers[name]["settings"]["url"]).query)

    def path(self, name):
        return unquote(urlparse(self.browsers[name]["settings"]["url"]).path)

    def test_asset_files_exist(self):
        for name in self.browsers:
            p = self.path(name)
            self.assertTrue(os.path.isfile(p), f"{name} points at missing {p}")

    def test_browser_size_matches_composited_size(self):
        """obs-browser renders offscreen at a fixed pixel size. If that does not
        match the box it is composited into, the asset is rescaled and blurs."""
        expect = {
            "BG · Starfield": (CANVAS_W, CANVAS_H),
            "UI · Top Bar": (CANVAS_W, TOPBAR_H),
            "UI · Lower Stack": (CANVAS_W, LOWER_H),
            "CARD · Title": (CANVAS_W, CANVAS_H),
            "CARD · Outro": (CANVAS_W, CANVAS_H),
            "CARD · Break": (CANVAS_W, CANVAS_H),
        }
        for name, (w, h) in expect.items():
            s = self.browsers[name]["settings"]
            self.assertEqual((s["width"], s["height"]), (w, h), name)

    def test_chrome_items_composited_at_native_size(self):
        """Local assets are 1:1 artwork, so any rescale is visible blur.
        Live video is exempt: the guest cam appears at 1896px wide in scene 03
        and ~290px in a rail, so no single offscreen size is native to both.
        It renders at 1080p and downscales, which is fine; upscaling is not."""
        for sc in scenes(self.col):
            for it in sc["settings"]["items"]:
                if it["name"] not in self.browsers:
                    continue
                s = self.browsers[it["name"]]["settings"]
                self.assertEqual((it["bounds"]["x"], it["bounds"]["y"]),
                                 (float(s["width"]), float(s["height"])),
                                 f'{sc["name"]}/{it["name"]} composited off-scale')

    def test_headline_slot_is_not_the_show_name(self):
        """Regression: lower_stack's `title` is the headline row. Feeding it the
        brand duplicates the wordmark already in the badge and the top bar."""
        title = self.params("UI · Lower Stack")["title"][0]
        show = self.params("UI · Top Bar")["show"][0]
        self.assertNotEqual(title.strip().upper(), show.strip().upper())

    def test_lower_stack_params(self):
        p = self.params("UI · Lower Stack")
        for key in ("title", "hosts", "episode", "chiragSite", "parthSite"):
            self.assertIn(key, p, f"lower stack missing {key}")

    def test_host_websites_are_wired_to_all_identity_panels(self):
        for name in ("UI · Lower Stack", "CARD · Title", "CARD · Outro", "CARD · Break"):
            self.assertEqual(self.params(name)["chiragSite"], ["lordpatil.com"])
            self.assertEqual(self.params(name)["parthSite"], ["parthshastri.co.in"])

    def test_brands_use_the_supplied_bev_artwork(self):
        for asset in ("lower_stack.html", "title_card.html", "outro_card.html"):
            with open(os.path.join(bs.ASSETS, asset)) as f:
                html = f.read()
            self.assertIn('src="bev-logo.svg"', html)
            self.assertIn("Lord Socks", html)
            self.assertIn("House of Lords", html)
            self.assertNotIn("Dev Drink", html)

    def test_params_are_url_encoded(self):
        """Pipes and spaces must survive the query string intact."""
        raw = self.browsers["UI · Lower Stack"]["settings"]["url"]
        self.assertNotIn("|", raw, "unencoded pipe in URL")
        self.assertNotIn(" ", raw, "unencoded space in URL")

    def test_cards_get_show_name(self):
        for name in ("CARD · Title", "CARD · Outro"):
            self.assertIn("show", self.params(name), name)

    def test_param_names_match_what_the_html_reads(self):
        """Greps the assets for readText("<name>"...) and asserts we only pass
        keys they actually consume. Catches typo'd params, which fail silently
        because readText just falls back to its default."""
        import re
        for src, asset in [("UI · Top Bar", "topbar.html"),
                           ("UI · Lower Stack", "lower_stack.html"),
                           ("CARD · Title", "title_card.html"),
                           ("CARD · Outro", "outro_card.html")]:
            with open(os.path.join(bs.ASSETS, asset)) as f:
                html = f.read()
            known = set(re.findall(r'readText\(\s*"([^"]+)"', html))
            known |= set(re.findall(r'params\.get\(\s*"([^"]+)"', html))
            known |= set(re.findall(r'data-copy="([^"]+)"', html))
            for key in self.params(src):
                self.assertIn(key, known,
                              f'{asset} never reads "{key}" - it will be ignored')


class TestRemoteGuest(unittest.TestCase):
    """The VDO.Ninja transport. Each of these pins a failure that is silent at
    build time and only shows up on air, or worse, in the recording."""

    @classmethod
    def setUpClass(cls):
        cls.col = collection()
        cls.by_name = sources_by_name(cls.col)
        cls.scenes = scenes(cls.col)
        cls.link = guest_link(ROOM, GUEST_ID, PASSWORD)

    def url(self, name):
        return self.by_name[name]["settings"]["url"]

    def query(self, name):
        """keep_blank_values, because &solo is a valueless flag and parse_qs
        drops those by default -- the exact way a test here could lie."""
        return parse_qs(urlparse(self.url(name)).query, keep_blank_values=True)

    # --- the one that matters most ------------------------------------------
    def test_guest_audio_is_active_in_every_scene(self):
        """OBS only produces audio from a source that is in the program scene
        AND visible. Cutting to a scene with no guest item silences the guest,
        and because the browser page stays loaded nothing looks wrong -- you
        discover the holes in the edit. Every scene therefore carries the guest
        feed, visibly, even when it is covered."""
        for sc in self.scenes:
            live = {it["name"] for it in sc["settings"]["items"] if it["visible"]}
            self.assertIn("CAM · Guest", live,
                          f'{sc["name"]}: guest audio is not active here')

    def test_carriers_sit_beneath_the_opaque_backing(self):
        """A carrier must be invisible to the viewer. Items are stored
        bottom-to-top, so it has to come before BG · Void in the list; if it
        ever floats above, a full-frame guest camera covers the whole scene."""
        for sc in self.scenes:
            names = [it["name"] for it in sc["settings"]["items"]]
            void = names.index("BG · Void")
            for i, it in enumerate(sc["settings"]["items"]):
                if it["private_settings"].get("frontier_role") == CARRIER:
                    self.assertLess(i, void,
                                    f'{sc["name"]}: carrier {it["name"]} is on top '
                                    "of the backing and will cover the scene")

    # --- link wiring ---------------------------------------------------------
    def test_guest_push_id_matches_what_obs_views(self):
        """If these drift apart the browser source renders an empty black box
        forever, with no error anywhere. A guest who joins with a bare room
        link also gets a random ID each session, which is why the link has to
        carry an explicit push."""
        sent = parse_qs(urlparse(self.link).query)
        self.assertEqual(sent["push"][0], GUEST_ID)
        self.assertEqual(self.query("CAM · Guest")["view"][0], GUEST_ID)
        self.assertEqual(sent["room"][0], self.query("CAM · Guest")["room"][0])

    def test_share_is_addressed_as_a_separate_stream(self):
        """The whole reason for moving off window-capture: the guest's screen
        must be its own stream, not the same window as their face."""
        self.assertEqual(self.query("SCREEN · Guest Share")["view"][0],
                         f"{GUEST_ID}:s")
        self.assertIn(f"view={GUEST_ID}:s", self.url("SCREEN · Guest Share"),
                      "the ':' got percent-encoded; vdo.ninja will not match it")

    def test_solo_is_a_bare_flag(self):
        """The docs are explicit that &solo takes no value. solo=1 is a
        different thing and silently does not apply."""
        for name in REMOTE:
            self.assertIn("&solo&", self.url(name) + "&", name)

    def test_links_are_not_cross_wired(self):
        """Sender-side and viewer-side params are not interchangeable: &record
        on a view link records nothing, and &cleanoutput on the guest's link
        strips the UI they need to start their share."""
        for name in REMOTE:
            q = self.query(name)
            self.assertNotIn("record", q, f"{name} view link carries &record")
            self.assertNotIn("push", q, f"{name} view link carries &push")
        sent = parse_qs(urlparse(self.link).query)
        self.assertNotIn("view", sent)
        self.assertNotIn("cleanoutput", sent)
        self.assertIn("record", sent, "guest link does not record locally")

    def test_password_reaches_both_ends(self):
        """A room without a password is walk-in-able by anyone who guesses the
        name. If the password reaches only one end, they simply cannot connect."""
        self.assertEqual(parse_qs(urlparse(self.link).query)["password"][0], PASSWORD)
        for name in REMOTE:
            self.assertEqual(self.query(name)["password"][0], PASSWORD)

    def test_no_credentials_are_baked_into_the_module(self):
        """Room and guest id are arguments, never module constants, so a build
        cannot silently fall back to someone's real room."""
        with open(bs.__file__) as f:
            src = f.read()
        self.assertNotIn("VDO_ROOM =", src)
        for bad in ("", None):
            with self.assertRaises(ValueError):
                build(bad, GUEST_ID)
            with self.assertRaises(ValueError):
                build(ROOM, bad)

    # --- browser-source settings --------------------------------------------
    def test_reroute_audio_and_mixers_agree(self):
        """mixers is silently ignored on a browser source unless reroute_audio
        is on. A test asserting only the bitmask would pass green while the
        audio went nowhere."""
        for s in self.col["sources"]:
            if s["id"] != "browser_source":
                continue
            self.assertEqual(bool(s["settings"]["reroute_audio"]),
                             bool(s["mixers"]),
                             f'{s["name"]}: reroute_audio and mixers disagree')

    def test_remote_sources_do_not_restart_on_activate(self):
        """Reloading a local asset is invisible. Reloading a WebRTC page tears
        down and renegotiates the peer connection, so this would give seconds
        of black on every cut into a scene holding the guest."""
        for name in REMOTE:
            self.assertFalse(
                self.by_name[name]["settings"]["restart_when_active"], name)

    def test_remote_sources_get_no_obs_control(self):
        """No reason to grant a third-party origin read access to OBS state."""
        for name in REMOTE:
            self.assertEqual(
                self.by_name[name]["settings"]["webpage_control_level"], 0, name)

    # --- the content slot -----------------------------------------------------
    def test_slot_holds_exactly_one_visible_screen(self):
        """Two visible screens would stack and hide one. Zero would show the
        void. The operator toggles between them inside this one scene."""
        slot = next(s for s in self.col["sources"] if s["name"] == SLOT_SCENE)
        items = slot["settings"]["items"]
        self.assertEqual({it["name"] for it in items},
                         {"SCREEN · Share", "SCREEN · Guest Share", "SCREEN · Parth Share"})
        self.assertEqual(sum(1 for it in items if it["visible"]), 1)

    def test_screen_scenes_go_through_the_slot(self):
        """Referencing a screen source directly would reintroduce the parallel
        scene-per-screen duplication the slot exists to avoid."""
        for name in ("05 Screen · Duo", "06 Screen Full", "08 Screen · Trio"):
            sc = next(s for s in self.scenes if s["name"] == name)
            names = {it["name"] for it in sc["settings"]["items"]}
            self.assertIn(SLOT_SCENE, names, name)
            self.assertNotIn("SCREEN · Share", names, name)

    def test_slot_is_not_reachable_by_hotkey(self):
        """It is a container, not a shot. If it entered scene_order it would
        also break the alphanumeric ordering that keeps F-keys predictable."""
        slot = next(s for s in self.col["sources"] if s["name"] == SLOT_SCENE)
        self.assertEqual(slot["hotkeys"], {})
        self.assertNotIn(SLOT_SCENE, [s["name"] for s in self.col["scene_order"]])
        self.assertTrue(slot["settings"]["custom_size"])
        self.assertEqual((slot["settings"]["cx"], slot["settings"]["cy"]),
                         (CANVAS_W, CANVAS_H))


class TestIdentifierSanitising(unittest.TestCase):
    """Regression cover for a live failure on 2026-09-14.

    vdo.ninja rewrites non-alphanumeric characters in a stream ID to "_", in
    the guest's browser, after the page loads. A guest given `guest-1234`
    publishes as `guest_1234`; OBS went on subscribing to the hyphen form and
    rendered a placeholder that looked like a real but blank camera. Neither
    end reported an error. The fix is to apply the same rule when generating,
    so the two links are derived from one already-normalised value."""

    def test_hyphen_becomes_underscore(self):
        """The exact transformation the docs specify, and the exact one that
        broke: "non-alphanumeric characters are sanitized to _"."""
        self.assertEqual(stream_id("guest-1a2b3c4d"), "guest_1a2b3c4d")

    def test_every_non_alphanumeric_is_replaced(self):
        for raw, want in (("a.b", "a_b"), ("a b", "a_b"), ("a/b", "a_b"),
                          ("a+b", "a_b"), ("a:b", "a_b"), ("é", "_")):
            with self.subTest(raw=raw):
                self.assertEqual(stream_id(raw), want)

    def test_already_clean_ids_are_untouched(self):
        self.assertEqual(stream_id("guest99e2aa73"), "guest99e2aa73")

    def test_case_is_preserved(self):
        """IDs are documented as case sensitive, so normalising case would
        break the match just as surely as the hyphen did."""
        self.assertEqual(stream_id("GuestABC"), "GuestABC")

    def test_sanitising_is_idempotent(self):
        once = stream_id("guest-1a2b3c4d")
        self.assertEqual(stream_id(once), once)

    def test_empty_and_overlong_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            stream_id("")
        with self.assertRaises(ValueError):
            stream_id("x" * 65)              # documented maximum is 64
        self.assertEqual(len(stream_id("x" * 64)), 64)

    def test_guest_link_and_obs_view_agree_on_a_dirty_id(self):
        """The whole point. Feed build() and guest_link() an id that vdo.ninja
        would rewrite, and the two ends must still name the same stream."""
        dirty = "guest-1a2b3c4d"
        col = build(ROOM, dirty, PASSWORD, parth_id=PARTH_ID)
        pushed = parse_qs(urlparse(guest_link(ROOM, dirty, PASSWORD)).query,
                          keep_blank_values=True)["push"][0]
        views = {s["name"]: parse_qs(urlparse(s["settings"]["url"]).query,
                                     keep_blank_values=True)["view"][0]
                 for s in col["sources"]
                 if "vdo.ninja" in s.get("settings", {}).get("url", "")}
        self.assertEqual(pushed, "guest_1a2b3c4d")
        self.assertEqual(views["CAM · Guest"], pushed)
        self.assertEqual(views["SCREEN · Guest Share"], pushed + ":s")

    def test_no_hyphen_survives_into_any_generated_link(self):
        """A hyphen anywhere in a stream id is the signature of the bug."""
        col = build(ROOM, "guest-1a2b3c4d", PASSWORD, parth_id=PARTH_ID)
        for s in col["sources"]:
            url = s.get("settings", {}).get("url", "")
            if "vdo.ninja" not in url:
                continue
            vid = parse_qs(urlparse(url).query, keep_blank_values=True)["view"][0]
            self.assertNotIn("-", vid, s["name"])

    def test_rooms_reject_rather_than_guess(self):
        """Rooms are documented as alphanumeric, with no stated behaviour for
        anything else. Relying on undefined behaviour is what caused this bug
        in the first place, so a dirty room is refused, not silently fixed."""
        for bad in ("frontier-5e6f7a8b", "front room", "front.room", ""):
            with self.subTest(room=bad), self.assertRaises(ValueError):
                check_room(bad)
        with self.assertRaises(ValueError):
            check_room("x" * 50)             # documented maximum is 49

    def test_clean_rooms_pass_through_unchanged(self):
        self.assertEqual(check_room("frontiere9fe3ae0"), "frontiere9fe3ae0")

    def test_build_refuses_a_dirty_room(self):
        with self.assertRaises(ValueError):
            build("frontier-5e6f7a8b", GUEST_ID, PASSWORD)


class TestDuoStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.col = collection()
        cls.by_name = sources_by_name(cls.col)

    def scene_feeds(self, name):
        return {it["name"] for it in cells(self.by_name[name])}

    def test_duo_is_default_in_both_program_and_preview(self):
        self.assertEqual(self.col["current_scene"], "04 Duo")
        self.assertEqual(self.col["current_program_scene"], "04 Duo")
        self.assertEqual(self.scene_feeds("04 Duo"), {"CAM · Chirag", "CAM · Parth"})

    def test_trio_has_three_distinct_participants(self):
        self.assertEqual(self.scene_feeds("07 Trio · With Guest"),
                         {"CAM · Chirag", "CAM · Parth", "CAM · Guest"})

    def test_screen_views_keep_the_hosts_and_add_optional_guest(self):
        self.assertEqual(self.scene_feeds("05 Screen · Duo"),
                         {"SLOT · Content", "CAM · Chirag", "CAM · Parth"})
        self.assertEqual(self.scene_feeds("08 Screen · Trio"),
                         {"SLOT · Content", "CAM · Chirag", "CAM · Parth", "CAM · Guest"})

    def test_all_audio_inputs_remain_active_in_every_scene(self):
        expected = {"MIC · Chirag", "CAM · Parth", "SCREEN · Parth Share",
                    "CAM · Guest", "SCREEN · Guest Share"}
        for scene in scenes(self.col):
            active = {it["name"] for it in scene["settings"]["items"] if it["visible"]}
            self.assertTrue(expected <= active, scene["name"])

    def test_stream_ids_cannot_collapse_to_the_same_feed(self):
        for parth in (GUEST_ID, "guest-id"):
            guest = GUEST_ID if parth == GUEST_ID else "guest_id"
            with self.assertRaises(ValueError):
                build(ROOM, guest, PASSWORD, parth_id=parth)

    def test_parth_id_is_required(self):
        with self.assertRaises(ValueError):
            build(ROOM, GUEST_ID, PASSWORD)

    def test_parth_invitation_and_views_match(self):
        link = guest_link(ROOM, PARTH_ID, PASSWORD)
        pushed = parse_qs(urlparse(link).query)["push"][0]
        cam = self.by_name["CAM · Parth"]["settings"]["url"]
        share = self.by_name["SCREEN · Parth Share"]["settings"]["url"]
        self.assertEqual(parse_qs(urlparse(cam).query)["view"][0], pushed)
        self.assertEqual(parse_qs(urlparse(share).query)["view"][0], pushed + ":s")

    def test_labels_stay_within_their_camera_cells(self):
        for scene in scenes(self.col):
            items = scene["settings"]["items"]
            for item in items:
                if not item["name"].startswith("UI · ") or " Label " not in item["name"]:
                    continue
                person = item["name"].split(" · ")[1].split(" Label ")[0]
                feed = next(it for it in cells(scene) if it["name"] == f"CAM · {person}")
                x0, y0, x1, y1 = box(item)
                fx0, fy0, fx1, fy1 = box(feed)
                self.assertTrue(fx0 <= x0 < x1 <= fx1)
                self.assertTrue(fy0 <= y0 < y1 <= fy1)
                self.assertGreater(items.index(item), items.index(feed))

    def test_episode_and_guest_copy_reaches_sources(self):
        col = build(ROOM, GUEST_ID, PASSWORD, parth_id=PARTH_ID,
                    episode="12", title="Do machines understand?",
                    guest_name="A Guest", guest_role="Researcher")
        sources = sources_by_name(col)
        lower = parse_qs(urlparse(sources["UI · Lower Stack"]["settings"]["url"]).query)
        self.assertEqual(lower["title"], ["Do machines understand?"])
        self.assertEqual(lower["episode"], ["12"])
        labels = [s for name, s in sources.items() if name.startswith("UI · Guest Label")]
        self.assertTrue(labels)
        for source in labels:
            query = parse_qs(urlparse(source["settings"]["url"]).query)
            self.assertEqual(query["name"], ["A Guest"])
            self.assertEqual(query["role"], ["Researcher"])

    def test_profile_enables_all_six_tracks(self):
        with open(os.path.join(os.path.dirname(bs.__file__), "apply_profile.sh")) as f:
            profile = f.read()
        self.assertIn("TRACKS=63", profile)

    def test_local_brand_fonts_and_licenses_exist(self):
        for family in ("Anybody", "DelaGothicOne", "FragmentMono"):
            font = os.path.join(bs.ASSETS, "fonts", family + ".ttf")
            self.assertGreater(os.path.getsize(font), 1000)
            self.assertTrue(os.path.isfile(os.path.join(bs.ASSETS, "fonts", family + "-OFL.txt")))


class TestLocalHostSelection(unittest.TestCase):
    def variants(self):
        for host in ("chirag", "parth"):
            yield host, build(ROOM, GUEST_ID, PASSWORD, parth_id=PARTH_ID,
                              chirag_id="testchirag", local_host=host)

    def test_collection_names_are_distinct_and_both_open_on_duo(self):
        names = set()
        for host, col in self.variants():
            names.add(col["name"])
            self.assertEqual(col["name"], f"WTF · {host.title()} local")
            self.assertEqual(col["current_scene"], "04 Duo")
            self.assertEqual(col["current_program_scene"], "04 Duo")
        self.assertEqual(len(names), 2)

    def test_only_selected_host_has_local_camera_and_microphone(self):
        for host, col in self.variants():
            local = host.title()
            remote = "Parth" if host == "chirag" else "Chirag"
            sources = sources_by_name(col)
            self.assertEqual(sources[f"CAM · {local}"]["id"], "macos-avcapture")
            self.assertEqual(sources[f"MIC · {local}"]["id"], "coreaudio_input_capture")
            self.assertEqual(sources[f"CAM · {remote}"]["id"], "browser_source")
            self.assertNotIn(f"MIC · {remote}", sources)
            self.assertEqual(sum(s["id"] == "coreaudio_input_capture" for s in col["sources"]), 1)

    def test_voice_tracks_stay_attached_to_people(self):
        for host, col in self.variants():
            sources = sources_by_name(col)
            for person, bit in (("chirag", bs.TRACK_1), ("parth", bs.TRACK_4)):
                source = f"MIC · {person.title()}" if host == person else f"CAM · {person.title()}"
                self.assertEqual(sources[source]["mixers"], bit | bs.TRACK_6)
            for index in range(5):
                self.assertEqual(sum(bool(s["mixers"] & (1 << index)) for s in col["sources"]), 1)

    def test_remote_host_uses_the_correct_stream_and_share(self):
        for host, col in self.variants():
            person, sid = ("Parth", PARTH_ID) if host == "chirag" else ("Chirag", "testchirag")
            sources = sources_by_name(col)
            for name, stream in ((f"CAM · {person}", sid), (f"SCREEN · {person} Share", sid + ":s")):
                source = sources[name]
                query = parse_qs(urlparse(source["settings"]["url"]).query)
                self.assertEqual(query["view"], [stream])
                self.assertEqual(query["password"], [PASSWORD])
                self.assertFalse(source["settings"]["restart_when_active"])
                self.assertFalse(source["settings"]["shutdown"])
            self.assertEqual(sources[f"SCREEN · {person} Share"]["mixers"], bs.TRACK_5 | bs.TRACK_6)

    def test_active_audio_carriers_follow_the_selected_local_host(self):
        for host, col in self.variants():
            local = host.title()
            remote = "Parth" if host == "chirag" else "Chirag"
            expected = {f"MIC · {local}", f"CAM · {remote}", f"SCREEN · {remote} Share",
                        "CAM · Guest", "SCREEN · Guest Share"}
            for scene in scenes(col):
                items = scene["settings"]["items"]
                backing = next(i for i, item in enumerate(items) if item["name"] == "BG · Void")
                carriers = [item for item in items if item["private_settings"].get("frontier_role") == CARRIER]
                self.assertEqual({item["name"] for item in carriers}, expected)
                for item in carriers:
                    self.assertTrue(item["visible"])
                    self.assertLess(items.index(item), backing)

    def test_content_slot_defaults_to_local_screen_and_offers_remote_host_share(self):
        for host, col in self.variants():
            remote = "Parth" if host == "chirag" else "Chirag"
            slot = sources_by_name(col)[SLOT_SCENE]["settings"]["items"]
            self.assertEqual({item["name"] for item in slot},
                             {"SCREEN · Share", f"SCREEN · {remote} Share", "SCREEN · Guest Share"})
            self.assertEqual([item["name"] for item in slot if item["visible"]], ["SCREEN · Share"])

    def test_host_change_preserves_all_scene_geometry_and_identity_labels(self):
        chirag, parth = [col for _, col in self.variants()]
        a, b = sources_by_name(chirag), sources_by_name(parth)
        self.assertEqual(chirag["scene_order"], parth["scene_order"])
        for name in [entry["name"] for entry in chirag["scene_order"]]:
            def visible_geometry(scene):
                return [(item["name"], box(item)) for item in scene["settings"]["items"]
                        if item["private_settings"].get("frontier_role") != CARRIER]
            self.assertEqual(visible_geometry(a[name]), visible_geometry(b[name]))
        for name, source in a.items():
            if " Label " in name:
                self.assertEqual(source["settings"]["url"], b[name]["settings"]["url"])

    def test_parth_local_does_not_require_a_parth_stream_id(self):
        col = build(ROOM, GUEST_ID, PASSWORD, chirag_id="testchirag", local_host="parth")
        self.assertEqual(col["name"], "WTF · Parth local")

    def test_invalid_local_host_is_rejected(self):
        with self.assertRaises(ValueError):
            build(ROOM, GUEST_ID, PASSWORD, parth_id=PARTH_ID, local_host="guest")

    def test_remote_chirag_id_is_required_for_parth_local(self):
        with self.assertRaises(ValueError):
            build(ROOM, GUEST_ID, PASSWORD, parth_id=PARTH_ID, local_host="parth")

    def test_normalized_ids_must_be_distinct(self):
        with self.assertRaises(ValueError):
            build(ROOM, "test_guest", PASSWORD, chirag_id="test-guest", local_host="parth")

    def cli(self, *args, **changes):
        env = dict(os.environ, VDO_ROOM=ROOM, VDO_GUEST_ID=GUEST_ID,
                   VDO_PARTH_ID=PARTH_ID, VDO_CHIRAG_ID="testchirag", VDO_PASSWORD=PASSWORD)
        env.update(changes)
        return subprocess.run([sys.executable, bs.__file__, *args],
                              env=env, capture_output=True, text=True)

    def test_cli_builds_both_importable_collections(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.cli("--both-local-hosts", "-o", os.path.join(d, "podcast_scenes.json"))
            self.assertEqual(result.returncode, 0, result.stderr)
            for host in ("chirag", "parth"):
                with open(os.path.join(d, f"podcast_scenes_{host}_local.json")) as f:
                    col = json.load(f)
                self.assertEqual(col["name"], f"WTF · {host.title()} local")

    def test_cli_builds_parth_local_without_parth_id(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "parth.json")
            result = self.cli("--local-host", "parth", "-o", target, VDO_PARTH_ID="")
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(target) as f:
                self.assertEqual(json.load(f)["name"], "WTF · Parth local")

    def test_dual_generation_validates_before_writing_any_file(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.cli("--both-local-hosts", "-o", os.path.join(d, "podcast_scenes.json"),
                              VDO_CHIRAG_ID=GUEST_ID)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(os.listdir(d), [])

    def test_chirag_link_does_not_require_unrelated_ids(self):
        result = self.cli("--chirag-link", VDO_GUEST_ID="", VDO_PARTH_ID="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(parse_qs(urlparse(result.stdout.strip()).query)["push"], ["testchirag"])

    def test_preview_reflects_local_host_without_remote_connections(self):
        from preview_studio import preview_data
        for host in ("chirag", "parth"):
            data = preview_data(host)
            duo = next(scene for scene in data if scene["name"] == "04 Duo")
            cameras = [item for item in duo["items"] if item["name"].startswith("CAM · ")]
            local = [item["name"] for item in cameras if item["capture"] == "Local camera"]
            self.assertEqual(local, [f"CAM · {host.title()}"])
            self.assertNotIn("vdo.ninja", json.dumps(data))


class TestRecordingVerification(unittest.TestCase):
    """Exercise the real shell verifier with deterministic media-tool fixtures."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = os.path.join(self.tmp.name, "bin")
        os.mkdir(self.bin)
        fixtures = {
            "ffprobe": 'import os\nprint("\\n".join(str(i) for i in range(int(os.environ.get("WTF_TEST_TRACKS", "6")))))\n',
            "ffmpeg": 'import os, sys\nindex = sys.argv[sys.argv.index("-map") + 1].split(":")[-1]\nsilent = index in os.environ.get("WTF_TEST_SILENT", "1,2,4").split(",")\nprint("mean_volume: -91 dB" if silent else "mean_volume: -20 dB", file=sys.stderr)\nprint("max_volume: -inf dB" if silent else "max_volume: -8 dB", file=sys.stderr)\n',
        }
        for name, body in fixtures.items():
            filename = os.path.join(self.bin, name)
            with open(filename, "w") as f:
                f.write("#!" + sys.executable + "\n" + body)
            os.chmod(filename, 0o700)
        self.recording = os.path.join(self.tmp.name, "test.mkv")
        with open(self.recording, "w"):
            pass

    def verify(self, guest=False, silent="1,2,4", tracks="6"):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"],
                   WTF_TEST_SILENT=silent, WTF_TEST_TRACKS=tracks)
        script = os.path.join(os.path.dirname(bs.__file__), "verify_recording.sh")
        return subprocess.run(["bash", script] + (["--guest"] if guest else []) +
                              [self.recording], env=env, capture_output=True, text=True)

    def test_duo_allows_idle_guest_and_share_tracks(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("idle", result.stdout)

    def test_duo_requires_parth(self):
        self.assertEqual(self.verify(silent="1,2,3,4").returncode, 1)

    def test_duo_requires_chirag(self):
        self.assertEqual(self.verify(silent="0,1,2,4").returncode, 1)

    def test_guest_mode_requires_guest_voice(self):
        self.assertEqual(self.verify(guest=True).returncode, 1)

    def test_guest_mode_allows_idle_screen_audio(self):
        result = self.verify(guest=True, silent="2,4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_safety_mix_is_required(self):
        self.assertEqual(self.verify(silent="1,2,4,5").returncode, 1)

    def test_old_four_track_files_are_rejected(self):
        result = self.verify(tracks="4")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected six tracks", result.stdout)


class TestPreviewAndCLI(unittest.TestCase):
    def test_preview_does_not_include_remote_urls_or_credentials(self):
        from preview_studio import preview_data
        data = preview_data()
        text = json.dumps(data)
        self.assertNotIn("vdo.ninja", text)
        self.assertNotIn("password", text)
        self.assertEqual(len(data), 12)
        self.assertTrue(all("carrier" not in str(scene) for scene in data))

    def test_cli_writes_duo_collection_with_episode_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            output = os.path.join(d, "scenes.json")
            env = dict(os.environ, VDO_ROOM=ROOM, VDO_GUEST_ID=GUEST_ID,
                       VDO_PARTH_ID=PARTH_ID, VDO_PASSWORD=PASSWORD)
            result = subprocess.run([sys.executable, bs.__file__, "-o", output,
                                     "--episode", "42", "--title", "A new horizon"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(output) as f:
                col = json.load(f)
            self.assertEqual(col["current_program_scene"], "04 Duo")
            lower = sources_by_name(col)["UI · Lower Stack"]
            self.assertEqual(parse_qs(urlparse(lower["settings"]["url"]).query)["episode"], ["42"])

    def test_cli_cohost_link_uses_its_own_id(self):
        env = dict(os.environ, VDO_ROOM=ROOM, VDO_GUEST_ID=GUEST_ID,
                   VDO_PARTH_ID=PARTH_ID, VDO_PASSWORD=PASSWORD)
        result = subprocess.run([sys.executable, bs.__file__, "--parth-link"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_qs(urlparse(result.stdout.strip()).query)["push"], [PARTH_ID])


if __name__ == "__main__":
    unittest.main(verbosity=2)
