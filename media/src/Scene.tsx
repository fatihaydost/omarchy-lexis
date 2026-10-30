import { AbsoluteFill, Easing, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

export const FPS = 30;
const SRC_W = 1920;
const SRC_H = 1080;
const PAD = 28;
const RADIUS = 14;
const FADE_SEC = 0.4;

type Keyframe = { atSec: number; x: number; y: number; w: number; h: number };
export type SceneConfig = {
  clip: string;
  outWidth: number;
  aspect?: number; // width / height; ignored when outHeight is set
  outHeight?: number;
  trim: { startSec: number; endSec: number };
  camera: Keyframe[];
  captions?: { fromSec: number; toSec: number; text: string }[];
  fade?: boolean;
  gif?: { fps?: number; colors?: number };
};

const even = (n: number) => Math.round(n / 2) * 2;
export const sceneSize = (s: SceneConfig) => ({
  width: even(s.outWidth),
  height: even(s.outHeight ?? s.outWidth / (s.aspect ?? 16 / 9)),
});

const calm = Easing.inOut(Easing.cubic);

export const Scene = (s: SceneConfig) => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();
  const t = frame / FPS;

  // Camera: per-segment ease-in-out between keyframes, held before the first / after the last.
  const kf = [...s.camera].sort((a, b) => a.atSec - b.atSec);
  const cam = (k: 'x' | 'y' | 'w' | 'h') =>
    kf.length === 1
      ? kf[0][k]
      : interpolate(t, kf.map((p) => p.atSec), kf.map((p) => p[k]), {
          easing: calm,
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
  const [x, y, w, h] = [cam('x'), cam('y'), cam('w'), cam('h')];

  // Fit the crop rect into the frame ("cover"), centred on the rect.
  const fw = width - PAD * 2;
  const fh = height - PAD * 2;
  const k = Math.max(fw / w, fh / h);
  const left = fw / 2 - (x + w / 2) * k;
  const top = fh / 2 - (y + h / 2) * k;

  const fadeFrames = Math.round(FADE_SEC * FPS);
  const opacity =
    s.fade === false
      ? 1
      : interpolate(frame, [0, fadeFrames, durationInFrames - fadeFrames, durationInFrames], [0, 1, 1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

  const caption = s.captions?.find((c) => t >= c.fromSec && t < c.toSec);

  return (
    <AbsoluteFill style={{ background: 'radial-gradient(ellipse at 50% 40%, #171717 0%, #111111 55%, #0c0c0c 100%)' }}>
      <div
        style={{
          position: 'absolute',
          left: PAD,
          top: PAD,
          width: fw,
          height: fh,
          borderRadius: RADIUS,
          overflow: 'hidden',
          opacity,
          boxShadow: '0 18px 48px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.05)',
        }}
      >
        <OffthreadVideo
          src={staticFile(`clips/${s.clip}`)}
          trimBefore={Math.round(s.trim.startSec * FPS)}
          muted
          style={{ position: 'absolute', left, top, width: SRC_W * k, height: SRC_H * k, maxWidth: 'none' }}
        />
        {caption && (
          <div
            style={{
              position: 'absolute',
              left: 14,
              bottom: 14,
              padding: '5px 11px',
              borderRadius: 999,
              background: 'rgba(10,10,10,0.55)',
              color: 'rgba(255,255,255,0.8)',
              fontFamily: '"JetBrains Mono", "JetBrainsMono Nerd Font", "IBM Plex Mono", ui-monospace, monospace',
              fontSize: 13,
              letterSpacing: 0.2,
            }}
          >
            {caption.text}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
