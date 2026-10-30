// Usage: node render.mjs [name...]  (no names = all scenes in scenes.json)
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname);
const scenes = JSON.parse(readFileSync(path.join(root, 'scenes.json'), 'utf8'));
const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(scenes);
for (const n of names) if (!scenes[n]) throw new Error(`unknown scene "${n}"; known: ${Object.keys(scenes).join(', ')}`);

// Remotion downloads its own headless shell; set REMOTION_BROWSER (e.g. /usr/bin/brave) to use a local Chromium instead.
const browserExecutable = process.env.REMOTION_BROWSER || null;
const outDir = path.join(root, 'out');
const assetsDir = path.join(root, '..', 'assets');
mkdirSync(outDir, { recursive: true });
mkdirSync(assetsDir, { recursive: true });

const serveUrl = await bundle({ entryPoint: path.join(root, 'src/index.ts') });

for (const name of names) {
  const t0 = Date.now();
  const { outWidth, gif = {} } = scenes[name];
  const fps = gif.fps ?? 12;
  const colors = gif.colors ?? 192;
  const mp4 = path.join(outDir, `${name}.mp4`);
  const gifPath = path.join(assetsDir, `${name}.gif`);

  const composition = await selectComposition({ serveUrl, id: name, browserExecutable });
  // scale 2 renders at 2x, then lanczos downscales to outWidth for crisper text.
  await renderMedia({ serveUrl, composition, codec: 'h264', crf: 14, scale: 2, outputLocation: mp4, browserExecutable });

  const vf = `fps=${fps},scale=${outWidth}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=${colors}:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle`;
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', mp4, '-vf', vf, '-loop', '0', gifPath], { stdio: 'inherit' });

  const kb = (statSync(gifPath).size / 1024).toFixed(0);
  console.log(`${name}: ${path.relative(root, gifPath)}  ${kb} KB  (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
}
