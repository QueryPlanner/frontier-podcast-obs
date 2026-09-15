#!/usr/bin/env python3
"""Build a local, credential-free preview from the actual OBS scene geometry."""
import argparse
import json
from pathlib import Path

from build_scenes import build, CARRIER


def preview_data(local_host="chirag", font_variant=None):
    collection = build("previewroom", "previewguest", parth_id="previewparth",
                       chirag_id="previewchirag", local_host=local_host,
                       font_variant=font_variant)
    sources = {source["name"]: source for source in collection["sources"]}
    result = []
    for entry in collection["scene_order"]:
        scene = sources[entry["name"]]
        items = []
        for item in scene["settings"]["items"]:
            if item["private_settings"].get("frontier_role") == CARRIER:
                continue
            source = sources[item["name"]]
            record = dict(name=item["name"], x=item["pos"]["x"], y=item["pos"]["y"],
                          w=item["bounds"]["x"], h=item["bounds"]["y"])
            if item["name"].startswith("CAM · "):
                record["capture"] = "Local camera" if source["id"] == "macos-avcapture" else "Remote camera"
            if source["id"] == "browser_source" and "vdo.ninja" not in source["settings"]["url"]:
                url = source["settings"]["url"]
                # Keep the preview relocatable with the assets beside it.
                record["url"] = "../assets/" + url.split("/assets/", 1)[1]
            elif source["id"] == "color_source_v3":
                color = source["settings"]["color"]
                record["color"] = f"rgb({color & 255},{(color >> 8) & 255},{(color >> 16) & 255})"
            items.append(record)
        result.append(dict(name=scene["name"], items=items))
    return result


def render(font_variant=None):
    template = Path(__file__).with_name("preview_template.html").read_text()
    output = Path(__file__).with_name("render")
    output.mkdir(exist_ok=True)
    path = output / "studio-preview.html"
    choices = {host: preview_data(host, font_variant)
               for host in ("chirag", "parth")}
    path.write_text(template.replace("__COLLECTION_DATA__", json.dumps(choices)))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview the WTF OBS studio.")
    parser.add_argument("--font", dest="font_variant",
                        help="font variant key from assets/font-config.js")
    args = parser.parse_args()
    print(render(args.font_variant))
