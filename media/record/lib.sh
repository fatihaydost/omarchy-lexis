# Helpers for make_media.sh. Coordinates are physical pixels on a 1920x1080 eDP-1 at scale 1.25,
# placed at x=3200 in the Hyprland layout; change MON_X / MON_SCALE for another setup.
MON=${MON:-eDP-1}
MON_X=${MON_X:-3200}
MON_SCALE_NUM=4; MON_SCALE_DEN=5   # 1 / 1.25
DEMO=~/.cache/lexis-demo
REPO=${0:A:h:h:h}

mv_() { hyprctl dispatch "hl.dsp.cursor.move({x=$((MON_X + $1 * MON_SCALE_NUM / MON_SCALE_DEN)),y=$(($2 * MON_SCALE_NUM / MON_SCALE_DEN))})" >/dev/null; }
glide() { # x0 y0 x1 y1 steps
  local i; for i in $(seq 1 $5); do mv_ $(( $1 + ($3 - $1) * i / $5 )) $(( $2 + ($4 - $2) * i / $5 )); sleep 0.016; done; }
click() { mv_ $1 $2; sleep 0.05; ydotool click 0xC0 >/dev/null; }
dclick() { mv_ $1 $2; sleep 0.05; ydotool click 0xC0 >/dev/null; sleep 0.08; ydotool click 0xC0 >/dev/null; }
dnd_on() { [ "$(omarchy-shell notifications toggleDnd 2>/dev/null)" = "on" ] || omarchy-shell notifications toggleDnd >/dev/null; }

# Restart omarchy-shell with Lexis pointed at the demo data (your real data is never touched)
relaunch_demo() {
  local cfg=/usr/share/omarchy/shell
  while timeout 30 quickshell kill -p "$cfg" --any-display >/dev/null 2>&1; do :; done; sleep 1
  hyprctl dispatch "hl.dsp.exec_cmd(\"env $(tr '\n' ' ' < $DEMO/env) omarchy-launch-shell\")" >/dev/null
  for i in $(seq 1 80); do omarchy-shell shell ping >/dev/null 2>&1 && break; sleep 0.5; done; sleep 2
}

# Reseed the demo database and settings so every scenario starts from the same screen
fresh() {
  ( set -a; . $DEMO/env; set +a; rm -rf $DEMO/data/*(N) $DEMO/config/*(N) $DEMO/state/*(N)
    python3 -I $REPO/media/record/seed_demo.py $REPO >/dev/null )
  relaunch_demo
  hyprctl dispatch 'hl.dsp.focus({workspace=9})' >/dev/null
}
