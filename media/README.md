# Lexis README media

Turns real screen recordings of the plugin into the GIFs and screenshots used in `../README.md`.

1. `npm install` (once). Remotion fetches its own headless Chromium on first render;
   to use a local one instead: `REMOTION_BROWSER=/usr/bin/brave node render.mjs`.
2. `zsh record/make_media.sh` restarts omarchy-shell with Lexis pointed at sample data in
   `~/.cache/lexis-demo` (`record/seed_demo.py`: the starter deck plus 30 days of answers),
   records each scenario into `public/clips/<name>.mp4`, takes the main-window screenshots,
   restarts the shell on your own data and renders the GIFs. Pass scenario names to run only some:
   `zsh record/make_media.sh flow capture stills`. Needs `wf-recorder`, `ydotool` with `ydotoold`
   running, `grim`, `ffmpeg` and `node`; coordinates assume the screen described in `record/lib.sh`.
3. Edit `scenes.json`: one entry per GIF (`flow`, `capture`).
   `trim` picks the clip range; `camera` keyframes are crop rectangles in source pixels,
   timed in seconds from the trim start, eased in-out between them. Keep each rect's w/h
   close to the frame's aspect. `captions` are optional; `fade: false` disables the 0.4 s fades;
   `gif` overrides `fps` (12) and palette `colors` (192).
4. Preview with `npx remotion studio src/index.ts`.
5. Render: `node render.mjs` (all) or `node render.mjs flow`.
   MP4s land in `out/`, GIFs in `../assets/<name>.gif`, with their size printed.
