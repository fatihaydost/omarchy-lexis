#!/bin/zsh
# Regenerates the README screenshots and GIFs from the real plugin running in omarchy-shell.
# Run with: zsh media/record/make_media.sh [flow capture stills]
# Needs wf-recorder, ydotool with ydotoold running, tesseract, imagemagick, ffmpeg, node.
# It takes over the screen for ~2 minutes on an empty workspace (9) with sample data in ~/.cache/lexis-demo,
# then restarts omarchy-shell on your own data. Coordinates assume a 1920x1080 panel at scale 1.25.
set -eu
. ${0:A:h}/lib.sh
CLIPS=$REPO/media/public/clips
mkdir -p $CLIPS $REPO/assets $DEMO/{data,config,state}

cat > $DEMO/env <<EOF
LEXIS_DB=$DEMO/data/lexis.sqlite
LEXIS_CONFIG=$DEMO/config/settings.json
LEXIS_STATE_DIR=$DEMO/state
EOF
cp ${0:A:h}/doc.html $DEMO/doc.html

# A calm reading window behind the card, so it is clear the card does not take the focus
hyprctl dispatch "hl.dsp.focus({monitor=\"$MON\"})" >/dev/null
hyprctl dispatch 'hl.dsp.focus({workspace=9})' >/dev/null
if ! hyprctl clients -j | grep -q lexis-demo_doc; then
  hyprctl dispatch "hl.dsp.exec_cmd(\"brave --user-data-dir=$DEMO/brave --no-first-run --no-default-browser-check --app=file://$DEMO/doc.html\")" >/dev/null
  sleep 4
fi

rec_start() { wf-recorder -y -o $MON -r 30 -f $CLIPS/$1.mp4 >/dev/null 2>&1 & RP=$!; sleep 1.2; }
rec_stop() { sleep 0.5; kill -INT $RP; wait $RP 2>/dev/null || true; }
# The main window is centred; crop rectangles are physical pixels
shot() { grim -o $MON - | ffmpeg -v error -y -i - -vf "crop=$2" $REPO/assets/$1.png; }
# Make a word due now without touching the screen, so the next question is a 4-choice one
# Clear any text selection left in the reading window from a previous run
deselect() { click 1100 950; sleep 0.2; }
make_due() { python3 -I -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE words SET due_at=0 WHERE word=?', (sys.argv[2],)); c.commit()" $DEMO/data/lexis.sqlite $1; }

sc_flow() {
  fresh; deselect; mv_ 1100 700; sleep 0.5
  rec_start flow
  sleep 0.8; omarchy-shell lexis askNow >/dev/null; sleep 3.2
  glide 1100 700 1682 291 22; click 1682 291; sleep 1.4
  make_due mitigate; omarchy-shell lexis askNow >/dev/null; sleep 2
  local y=$(env $(tr '\n' ' ' < $DEMO/env) python3 -I $REPO/media/record/choice_y.py)
  glide 1682 291 1600 $y 12; sleep 0.4; click 1600 $y; sleep 2.8
  glide 1600 $y 1100 700 20; sleep 1.2
  rec_stop
  omarchy-shell lexis dismissToast >/dev/null
}

sc_capture() {
  fresh; deselect; mv_ 1100 700; sleep 0.5
  rec_start capture
  sleep 0.8; glide 1100 700 515 412 22; sleep 0.3; dclick 515 412; sleep 0.8
  ydotool key 125:1 42:1 45:1 45:0 42:0 125:0 >/dev/null; sleep 2.6
  glide 515 412 1100 760 18; omarchy-shell lexis tab words >/dev/null; sleep 4.2
  rec_stop
  omarchy-shell lexis close >/dev/null; omarchy-shell lexis dismissToast >/dev/null
}

sc_stills() {
  fresh; mv_ 1900 1060
  omarchy-shell lexis panel >/dev/null; sleep 0.8
  for t in today words translate stats lists settings; do
    omarchy-shell lexis tab $t >/dev/null; sleep 1.3; mv_ 1900 1060; shot panel-$t "1308:858:306:128"
  done
  omarchy-shell lexis close >/dev/null
}

dnd_on
for s in ${@:-flow capture stills}; do sc_$s; done

# Back to your own data, notifications and workspace
for a in $(hyprctl clients -j | python3 -c 'import json,sys;[print(c["address"]) for c in json.load(sys.stdin) if "lexis-demo" in c["class"]]'); do
  hyprctl dispatch "hl.dsp.window.close({window=\"address:$a\"})" >/dev/null
done
omarchy-restart-shell >/dev/null 2>&1
sleep 4; [ "$(omarchy-shell notifications toggleDnd 2>/dev/null)" = "off" ] || omarchy-shell notifications toggleDnd >/dev/null

GIFS=(${${@:-flow capture}:#stills})
[ ${#GIFS} -gt 0 ] && cd $REPO/media && node render.mjs $GIFS
