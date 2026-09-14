#!/usr/bin/env python3
"""
Tests for the Frontier Podcast OBS scene collection and its HTML assets.

Two layers:

  * Geometry / schema tests run against the in-memory output of build(), so
    they never depend on a stale podcast_scenes.json on disk.
  * Render tests drive headless Chrome against the real asset files and assert
    on actual pixels. They skip (not fail) when Chrome is absent, so the
    geometry suite still runs on a machine without it.

Run:  python3 test_scenes.py
"""

import json
import os
import subprocess
import tempfile
import unittest
from urllib.parse import urlparse, parse_qs, unquote

import build_scenes as bs
from build_scenes import (
    CANVAS_W, CANVAS_H, TOPBAR_H, LOWER_H, BAND_Y, BAND_H,
    MARGIN, GAP, BORDER, CARRIER, build, guest_link, stream_id, check_room,
)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Fixtures, not real credentials. build() takes these as arguments precisely so
# the tests never depend on the operator's actual room being in the environment.
# Alphanumeric on purpose: these used to be "test-room"/"test-guest", which is
# the very shape vdo.ninja silently rewrites. See TestIdentifierSanitising.
ROOM, GUEST_ID, PASSWORD = "testroom", "testguest", "test-pw"

# Cells that hold a live video feed. Chrome (top bar, lower stack, cards) and
# the full-canvas backing layers are deliberately allowed outside the band.
# SLOT — Content is a nested scene, but it is composited exactly like a feed.
FEEDS = {"CAM — Me", "CAM — Guest", "SLOT — Content"}
BAND_ITEMS = FEEDS | {"UI — Cell Border"}

# Browser sources whose URL is a remote WebRTC feed rather than a local asset.
REMOTE = {"CAM — Guest", "SCREEN — Guest Share"}

# The slot is a source container, never something you cut to, so it is exempt
# from the layout rules that govern on-air scenes.
SLOT_SCENE = "SLOT — Content"


def collection():
    return build(ROOM, GUEST_ID, PASSWORD)


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
        self.assertEqual(BAND_Y, TOPBAR_H + 8)
        self.assertEqual(BAND_H, 614)
        self.assertEqual(BAND_Y + BAND_H, CANVAS_H - LOWER_H - 8)

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
                                     if m == "UI — Cell Border" and j < i]
                    self.assertTrue(
                        borders_below,
                        f'{sc["name"]}: feed {n} has no border beneath it')

    def test_border_is_three_px_larger_than_feed(self):
        for sc in self.scenes:
            items = sc["settings"]["items"]
            feeds = cells(sc)
            borders = [it for it in items if it["name"] == "UI — Cell Border"]
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
                live = (it["name"] in FEEDS
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
        sc = next(s for s in self.scenes if s["name"] == "09 Two Shot — Over/Under")
        feeds = cells(sc)
        self.assertEqual(len(feeds), 2)
        for f in feeds:
            x0, _, x1, _ = box(f)
            self.assertLessEqual(x0, lo, f'{f["name"]} left edge {x0} inside safe zone {lo}')
            self.assertGreaterEqual(x1, hi, f'{f["name"]} right edge {x1} inside safe zone {hi}')

    def test_three_column_keeps_content_largest(self):
        """The point of the 3-column layout is that shared content stays big.
        If a side rail ever gets wider than the centre, the layout has drifted."""
        sc = next(s for s in self.scenes if s["name"] == "05 Screen — 3 Column")
        by_name = {}
        for it in cells(sc):
            by_name.setdefault(it["name"], []).append(box(it))
        screen = by_name["SLOT — Content"][0]
        screen_w = screen[2] - screen[0]
        for rail in ("CAM — Me", "CAM — Guest"):
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
        self.assertEqual(self.by_name["MIC — Me"]["mixers"], 0b100001)           # 33
        self.assertEqual(self.by_name["CAM — Guest"]["mixers"], 0b100010)        # 34
        self.assertEqual(self.by_name["SCREEN — Guest Share"]["mixers"], 0b100100)  # 36

    def test_no_two_sources_claim_the_same_isolated_track(self):
        """The point of isolated tracks is that each holds exactly one voice.
        Two sources sharing track 2 would mix them together permanently, which
        no amount of editing can undo."""
        for track in (0, 1, 2):                      # tracks 1, 2, 3
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
            if names & {"CARD — Title", "CARD — Outro"}:
                continue
            self.assertIn("UI — Top Bar", names, sc["name"])
            self.assertIn("UI — Lower Stack", names, sc["name"])

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
            "BG — Starfield": (CANVAS_W, CANVAS_H),
            "UI — Top Bar": (CANVAS_W, TOPBAR_H),
            "UI — Lower Stack": (CANVAS_W, LOWER_H),
            "CARD — Title": (CANVAS_W, CANVAS_H),
            "CARD — Outro": (CANVAS_W, CANVAS_H),
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
        title = self.params("UI — Lower Stack")["title"][0]
        show = self.params("UI — Top Bar")["show"][0]
        self.assertNotEqual(title.strip().upper(), show.strip().upper())

    def test_lower_stack_params(self):
        p = self.params("UI — Lower Stack")
        for key in ("title", "hosts", "sponsors", "presentedBy"):
            self.assertIn(key, p, f"lower stack missing {key}")

    def test_sponsors_are_the_four_named(self):
        want = ["lordpatil.com", "Dev Drink", "Lord Socks", "House of Lords"]
        for name in ("UI — Lower Stack", "CARD — Outro"):
            got = self.params(name)["sponsors"][0].split("|")
            self.assertEqual(got, want, name)

    def test_sponsor_list_fits_the_four_slots(self):
        """Both assets slice to 4; a fifth sponsor would silently vanish."""
        for name in ("UI — Lower Stack", "CARD — Outro"):
            self.assertLessEqual(len(self.params(name)["sponsors"][0].split("|")), 4)

    def test_params_are_url_encoded(self):
        """Pipes and spaces must survive the query string intact."""
        raw = self.browsers["UI — Lower Stack"]["settings"]["url"]
        self.assertNotIn("|", raw, "unencoded pipe in URL")
        self.assertNotIn(" ", raw, "unencoded space in URL")

    def test_cards_get_show_name(self):
        for name in ("CARD — Title", "CARD — Outro"):
            self.assertIn("show", self.params(name), name)

    def test_param_names_match_what_the_html_reads(self):
        """Greps the assets for readText("<name>"...) and asserts we only pass
        keys they actually consume. Catches typo'd params, which fail silently
        because readText just falls back to its default."""
        import re
        for src, asset in [("UI — Top Bar", "topbar.html"),
                           ("UI — Lower Stack", "lower_stack.html"),
                           ("CARD — Title", "title_card.html"),
                           ("CARD — Outro", "outro_card.html")]:
            with open(os.path.join(bs.ASSETS, asset)) as f:
                html = f.read()
            known = set(re.findall(r'readText\(\s*"([^"]+)"', html))
            known |= set(re.findall(r'params\.get\(\s*"([^"]+)"', html))
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
            self.assertIn("CAM — Guest", live,
                          f'{sc["name"]}: guest audio is not active here')

    def test_carriers_sit_beneath_the_opaque_backing(self):
        """A carrier must be invisible to the viewer. Items are stored
        bottom-to-top, so it has to come before BG — Void in the list; if it
        ever floats above, a full-frame guest camera covers the whole scene."""
        for sc in self.scenes:
            names = [it["name"] for it in sc["settings"]["items"]]
            void = names.index("BG — Void")
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
        self.assertEqual(self.query("CAM — Guest")["view"][0], GUEST_ID)
        self.assertEqual(sent["room"][0], self.query("CAM — Guest")["room"][0])

    def test_share_is_addressed_as_a_separate_stream(self):
        """The whole reason for moving off window-capture: the guest's screen
        must be its own stream, not the same window as their face."""
        self.assertEqual(self.query("SCREEN — Guest Share")["view"][0],
                         f"{GUEST_ID}:s")
        self.assertIn(f"view={GUEST_ID}:s", self.url("SCREEN — Guest Share"),
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
                         {"SCREEN — Share", "SCREEN — Guest Share"})
        self.assertEqual(sum(1 for it in items if it["visible"]), 1)

    def test_screen_scenes_go_through_the_slot(self):
        """Referencing a screen source directly would reintroduce the parallel
        scene-per-screen duplication the slot exists to avoid."""
        for name in ("05 Screen — 3 Column", "06 Screen Full", "08 Screen + Guest"):
            sc = next(s for s in self.scenes if s["name"] == name)
            names = {it["name"] for it in sc["settings"]["items"]}
            self.assertIn(SLOT_SCENE, names, name)
            self.assertNotIn("SCREEN — Share", names, name)

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
        col = build(ROOM, dirty, PASSWORD)
        pushed = parse_qs(urlparse(guest_link(ROOM, dirty, PASSWORD)).query,
                          keep_blank_values=True)["push"][0]
        views = {s["name"]: parse_qs(urlparse(s["settings"]["url"]).query,
                                     keep_blank_values=True)["view"][0]
                 for s in col["sources"]
                 if "vdo.ninja" in s.get("settings", {}).get("url", "")}
        self.assertEqual(pushed, "guest_1a2b3c4d")
        self.assertEqual(views["CAM — Guest"], pushed)
        self.assertEqual(views["SCREEN — Guest Share"], pushed + ":s")

    def test_no_hyphen_survives_into_any_generated_link(self):
        """A hyphen anywhere in a stream id is the signature of the bug."""
        col = build(ROOM, "guest-1a2b3c4d", PASSWORD)
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


@unittest.skipUnless(os.path.isfile(CHROME), "headless Chrome not installed")
class TestAssetRender(unittest.TestCase):
    """Renders the real HTML at native size and asserts on pixels."""

    tmp = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Pillow not installed")

    @classmethod
    def tearDownClass(cls):
        if cls.tmp:
            cls.tmp.cleanup()

    @staticmethod
    def digest(im):
        """Compare renders by hash, not raw bytes: a failed assertEqual on
        multi-megabyte image bytes buries the actual message."""
        import hashlib
        return hashlib.sha256(im.tobytes()).hexdigest()[:16]

    def shot(self, asset, w, h, query="", budget=4000):
        out = os.path.join(self.tmp.name, f"{asset}-{abs(hash((query, budget)))}.png")
        url = "file://" + os.path.join(bs.ASSETS, asset) + query
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", f"--virtual-time-budget={budget}",
             f"--window-size={w},{h}", f"--screenshot={out}", url],
            capture_output=True, timeout=90, check=False)
        self.assertTrue(os.path.isfile(out), f"{asset} produced no render")
        from PIL import Image
        im = Image.open(out).convert("RGBA")
        self.assertEqual(im.size, (w, h), f"{asset} rendered at the wrong size")
        return im

    def test_topbar_background_is_transparent(self):
        """The top bar composites over live video. If it renders opaque it
        blacks out the full width of the frame."""
        im = self.shot("topbar.html", CANVAS_W, TOPBAR_H)
        w, h = im.size
        for p in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
            self.assertLess(im.getpixel(p)[3], 40,
                            f"top bar corner {p} is opaque")

    def test_topbar_renders_content(self):
        im = self.shot("topbar.html", CANVAS_W, TOPBAR_H).convert("L")
        bright = sum(1 for p in im.getdata() if p > 120)
        self.assertGreater(bright, 2000, "top bar looks blank")

    def test_ticker_never_slides_under_the_presented_by_chip(self):
        """Regression: the ticker window used to span the full 1920px, so
        sponsor names scrolled beneath the chip and were hard-sliced by its
        edge. The window is now inset and masked; sample several phases of the
        30s loop and assert the gap left of the chip stays empty."""
        from PIL import Image
        CHIP_LEFT = CANVAS_W - 22 - 240          # 1658, chip's white border
        gap_x = range(CHIP_LEFT - 28, CHIP_LEFT - 2)
        for t in (0, 3, 8, 14, 21, 27):
            im = self.shot("lower_stack.html", CANVAS_W, LOWER_H,
                           f"?t={t}").convert("L")
            worst = max(im.getpixel((x, y))
                        for y in range(LOWER_H - 82, LOWER_H - 2)
                        for x in gap_x)
            self.assertLess(worst, 90,
                            f"ticker text intrudes into the chip gap at t={t}s")

    def test_ticker_loop_is_seamless(self):
        """Two identical sets translated by exactly -50% means t=0 and t=30
        must be pixel-identical. Adding a third set would break this.

        Scoped to the ticker band: the badge orbit runs on its own 18s cycle,
        so the full frame is legitimately different at t=30."""
        band = (0, LOWER_H - 84, 1634, LOWER_H)      # the .ticker-window box
        a = self.shot("lower_stack.html", CANVAS_W, LOWER_H, "?t=0").crop(band)
        b = self.shot("lower_stack.html", CANVAS_W, LOWER_H, "?t=30").crop(band)
        self.assertEqual(self.digest(a), self.digest(b),
                         "ticker does not wrap seamlessly at the loop point")

    def test_lower_stack_shows_all_four_sponsors(self):
        """Rendered, not grepped: the static sponsor row must fit all four
        names without clipping. Checks each of the four columns has ink."""
        im = self.shot("lower_stack.html", CANVAS_W, LOWER_H, "?t=5").convert("L")
        # static sponsor row sits between the headline block and the ticker
        for i in range(4):
            x0, x1 = 300 + i * 420, 300 + i * 420 + 380
            x1 = min(x1, CANVAS_W - 1)
            ink = sum(1 for y in range(200, 250) for x in range(x0, x1)
                      if im.getpixel((x, y)) > 120)
            self.assertGreater(ink, 50, f"sponsor column {i} looks empty")

    def test_headline_param_reaches_the_render(self):
        """A wrong param name fails silently via readText's fallback, so prove
        the override actually changes pixels."""
        a = self.shot("lower_stack.html", CANVAS_W, LOWER_H, "?t=5")
        b = self.shot("lower_stack.html", CANVAS_W, LOWER_H,
                      "?t=5&title=ZZZZ%20DIFFERENT%20HEADLINE%20ZZZZ")
        self.assertNotEqual(self.digest(a), self.digest(b),
                            "title param did not change the headline row")

    def test_cards_animate_in_and_settle(self):
        """Both cards start empty and fade in. t=0 near-black, t=4 full."""
        for asset in ("title_card.html", "outro_card.html"):
            early = self.shot(asset, CANVAS_W, CANVAS_H, "?t=0").convert("L")
            late = self.shot(asset, CANVAS_W, CANVAS_H, "?t=4").convert("L")
            e = sum(1 for p in early.getdata() if p > 60)
            l = sum(1 for p in late.getdata() if p > 60)
            self.assertGreater(l, 20000, f"{asset} never becomes visible")
            self.assertGreater(l, e * 5, f"{asset} does not animate in")

    def test_animations_run_when_no_freeze_param_is_given(self):
        """Regression, and the one that matters most in production: the debug
        freeze branch used `Number(params.get("t"))`, but params.get returns
        null when absent and Number(null) is 0 -- finite and >= 0 -- so every
        asset froze at time zero in OBS. The intro rendered blank and the
        sponsor ticker never moved.

        Every earlier render test passed an explicit t=, so none caught it.
        This one must never pass a t param."""
        for asset in ("title_card.html", "outro_card.html"):
            live = self.shot(asset, CANVAS_W, CANVAS_H).convert("L")
            frozen = self.shot(asset, CANVAS_W, CANVAS_H, "?t=0").convert("L")
            self.assertNotEqual(
                self.digest(live), self.digest(frozen),
                f"{asset} with no t param renders identically to t=0 - "
                "animations are frozen")
            bright = sum(1 for p in live.getdata() if p > 60)
            self.assertGreater(bright, 20000,
                               f"{asset} renders blank without a freeze param")

    def test_ticker_moves_when_no_freeze_param_is_given(self):
        """Same root cause, seen from the sponsor row: sample the ticker band
        at two different virtual-time budgets and require the pixels to differ."""
        band = (0, LOWER_H - 84, 1634, LOWER_H)
        a = self.shot("lower_stack.html", CANVAS_W, LOWER_H, budget=1500).crop(band)
        b = self.shot("lower_stack.html", CANVAS_W, LOWER_H, budget=6000).crop(band)
        self.assertNotEqual(self.digest(a), self.digest(b),
                            "sponsor ticker is not moving without a t param")

    def test_cards_are_fully_opaque(self):
        """Cards are full-frame takeovers; any transparency would leak the
        scene behind them."""
        for asset in ("title_card.html", "outro_card.html", "starfield_bg.html"):
            im = self.shot(asset, CANVAS_W, CANVAS_H, "?t=4")
            lo, _ = im.getchannel("A").getextrema()
            self.assertEqual(lo, 255, f"{asset} is not fully opaque")


if __name__ == "__main__":
    unittest.main(verbosity=2)
