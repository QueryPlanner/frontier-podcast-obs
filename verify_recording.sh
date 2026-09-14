#!/bin/bash
# Report whether each audio track in a recording actually contains sound.
#
# The failure this exists to catch is silent in every sense: if reroute_audio
# does not deliver the guest's WebRTC audio, OBS still writes track 2 -- it
# just writes digital silence. The recording looks completely normal, has the
# expected track count, and plays back fine, because track 6 (the safety mix)
# carries your voice. You find out when you open the edit.
#
# Usage: ./verify_recording.sh ~/Movies/2026-09-14\ 17-02-11.mov
#        ./verify_recording.sh            # newest file in the OBS output dir
set -euo pipefail

REC_DIR="$HOME/Movies"

# Track numbers here are OBS's 1-based labels, matching the checkboxes in
# Settings > Output > Recording. ffmpeg indexes audio streams from 0, so the
# mapping is track N -> stream a:N-1 with all six tracks enabled. Reject a
# different track count before applying these positional labels.
EXPECTED=("Chirag mic" "Guest voice" "Guest screen audio" "Parth voice" "Parth screen audio" "Safety mix")
REQUIRED=(1 0 0 1 0 1)

# Guests and screen audio are optional in the default duo format.
if [ "${1:-}" = "--guest" ]; then
  REQUIRED[1]=1
  shift
fi

# A track carrying speech sits well above this. A track carrying nothing
# reports -91 dB (the noise floor of 16-bit silence) or literally -inf.
# -80 is comfortably between the two and needs no tuning.
SILENCE_DB=-80

if [ $# -ge 1 ]; then
  FILE="$1"
else
  FILE=$(ls -t "$REC_DIR"/*.mov "$REC_DIR"/*.mp4 "$REC_DIR"/*.mkv 2>/dev/null | head -1) \
    || { echo "ERROR: no recordings in $REC_DIR" >&2; exit 1; }
  echo "newest recording: $FILE"
fi
[ -f "$FILE" ] || { echo "ERROR: no such file: $FILE" >&2; exit 1; }

NTRACKS=$(ffprobe -v error -select_streams a -show_entries stream=index \
            -of csv=p=0 "$FILE" | wc -l | tr -d ' ')
echo "audio tracks found: $NTRACKS"
if [ "$NTRACKS" -ne 6 ]; then
  echo "ERROR: expected six tracks. Enable all six recording tracks in OBS."
  exit 1
fi
echo

FAILED=0
for ((i = 0; i < NTRACKS; i++)); do
  LABEL="${EXPECTED[$i]:-track $((i + 1))}"

  # volumedetect writes its summary to stderr at the end of a full decode
  # pass, so the whole file is scanned. -vn skips video, which makes this
  # fast enough to run on a 90-minute episode.
  #
  # Log level must be 'info': volumedetect reports through the normal logger,
  # not as an error, so -v error silently discards the very numbers we came
  # for -- and every track then reads as unmeasurable, which looks identical
  # to a real failure. -nostats suppresses the progress spam that info adds.
  OUT=$(ffmpeg -v info -nostats -i "$FILE" -map "0:a:$i" -vn \
          -af volumedetect -f null - 2>&1 || true)
  MEAN=$(printf '%s\n' "$OUT" | sed -n 's/.*mean_volume: \(.*\) dB/\1/p')
  PEAK=$(printf '%s\n' "$OUT" | sed -n 's/.*max_volume: \(.*\) dB/\1/p')
  [ -n "$MEAN" ] || { echo "  could not measure stream a:$i"; FAILED=1; continue; }

  # -inf compares as neither < nor > in awk, so test it explicitly first.
  if [ "$PEAK" = "-inf" ] || awk "BEGIN{exit !($PEAK < $SILENCE_DB)}"; then
    if [ "${REQUIRED[$i]}" -eq 1 ]; then
      STATUS="SILENT: required voice or mix is missing"
      FAILED=1
    else
      STATUS="idle: optional guest or screen audio"
    fi
  else
    STATUS="ok"
  fi
  printf '  a:%d  %-22s mean %8s dB   peak %8s dB   %s\n' \
         "$i" "$LABEL" "$MEAN" "$PEAK" "$STATUS"
done

echo
if [ "$FAILED" -eq 0 ]; then
  echo "All required tracks carry audio."
else
  echo "A required track is empty. Check the named mic or remote feed in OBS."
  echo "Track 6 is the safety mix; remote microphones must use reroute_audio."
  exit 1
fi
