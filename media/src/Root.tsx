import { Composition } from 'remotion';
import scenes from '../scenes.json';
import { Scene, FPS, sceneSize, type SceneConfig } from './Scene';

export const Root = () => (
  <>
    {Object.entries(scenes as Record<string, SceneConfig>).map(([name, s]) => {
      const { width, height } = sceneSize(s);
      return (
        <Composition
          key={name}
          id={name}
          component={Scene}
          fps={FPS}
          width={width}
          height={height}
          durationInFrames={Math.round((s.trim.endSec - s.trim.startSec) * FPS)}
          defaultProps={s}
        />
      );
    })}
  </>
);
