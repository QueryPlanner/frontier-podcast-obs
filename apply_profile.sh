#!/bin/bash
# Configure the OBS recording profile for multitrack podcast capture.
#
# Simple output mode cannot record more than one audio track, so isolated
# mic/call stems require Advanced mode. Everything below edits only the
# [Output], [AdvOut] and [Video] sections of the active profile.
#
# Safe to re-run. Backs up basic.ini first. Refuses to run while OBS is open,
# because OBS holds config in memory and rewrites it on quit.
set -euo pipefail

PROFILE="$HOME/Library/Application Support/obs-studio/basic/profiles/Untitled"
INI="$PROFILE/basic.ini"

if pgrep -x OBS >/dev/null; then
  echo "ERROR: OBS is running. Quit OBS completely, then re-run." >&2
  exit 1
fi
[ -f "$INI" ] || { echo "ERROR: no profile at $INI" >&2; exit 1; }

BACKUP="$INI.bak.$(date +%Y%m%d-%H%M%S)"
cp "$INI" "$BACKUP"
echo "backed up -> $BACKUP"

# Apple VT H264 Hardware Encoder, ID read from this machine's OBS log.
ENC="com.apple.videotoolbox.videoencoder.ave.avc"
# Tracks: Chirag, guest, guest share, Parth, Parth share, safety mix.
TRACKS=63

python3 - "$INI" "$ENC" "$TRACKS" <<'PY'
import configparser, sys
ini, enc, tracks = sys.argv[1], sys.argv[2], sys.argv[3]

# OBS ini keys are case-sensitive; stop configparser lowercasing them.
cp = configparser.ConfigParser()
cp.optionxform = str
cp.read(ini)

changes = {
    "Output":  {"Mode": "Advanced"},
    "AdvOut":  {"RecEncoder": enc,
                "RecTracks": tracks,
                "RecAudioEncoder": "CoreAudio_AAC",
                "RecType": "Standard"},
    # FPSType=0 means "common FPS", whose value lives in FPSCommon.
    "Video":   {"FPSType": "0", "FPSCommon": "30",
                "BaseCX": "1920", "BaseCY": "1080",
                "OutputCX": "1920", "OutputCY": "1080"},
    "Audio":   {"SampleRate": "48000"},
}

for section, kv in changes.items():
    if not cp.has_section(section):
        cp.add_section(section)
    for k, v in kv.items():
        old = cp.get(section, k, fallback="<unset>")
        if old != str(v):
            print(f"  [{section}] {k}: {old} -> {v}")
        cp.set(section, k, str(v))

with open(ini, "w") as f:
    cp.write(f, space_around_delimiters=False)
print("profile written")
PY

echo
echo "Done. Reopen OBS, then set by hand (encoder options are not in basic.ini):"
echo "  Settings > Output > Recording > Rate Control: CRF, CRF 18"
echo "  Settings > Output > Recording > check all six Audio Tracks"
