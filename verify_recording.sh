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
# mapping is track N -> stream a:N-1. Track 6 is not stream 5: OBS only writes
# the tracks you ticked, so with 1,2,3,6 enabled the file holds four streams
# and track 6 lands at a:3. That is why this reads positionally.
EXPECTED=("MIC — Me" "CAM — Guest" "SCREEN — Guest Share" "MIX — Safety")

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
if [ "$NTRACKS" -ne 4 ]; then
  echo "  WARNING: expected 4 (tracks 1, 2, 3, 6). Check that all four boxes"
  echo "  are ticked in Settings > Output > Recording."
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
    STATUS="SILENT  <-- nothing recorded on this track"
    FAILED=1
  else
    STATUS="ok"
  fi
  printf '  a:%d  %-22s mean %8s dB   peak %8s dB   %s\n' \
         "$i" "$LABEL" "$MEAN" "$PEAK" "$STATUS"
done

echo
if [ "$FAILED" -eq 0 ]; then
  echo "All tracks carry audio."
else
  echo "At least one track is empty. If it is 'CAM — Guest', reroute_audio is"
  echo "not delivering the WebRTC stream -- that is the unverified assumption"
  echo "in this setup, and track 6 is your fallback for the episode."
  exit 1
fi
