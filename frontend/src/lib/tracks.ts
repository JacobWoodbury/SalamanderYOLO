import type { FrameTracks, TracksPayload } from "../types";

export type PathPoint = { frame: number; x: number; y: number };

/** Per track id, ordered path points (one entry per frame where the id appears). */
export function buildPaths(data: TracksPayload): Map<number, PathPoint[]> {
  const paths = new Map<number, PathPoint[]>();
  for (const frame of data.frames) {
    for (const t of frame.tracks) {
      const [x1, y1, x2, y2] = t.xyxy;
      const x = (x1 + x2) / 2;
      const y = (y1 + y2) / 2;
      const list = paths.get(t.id) ?? [];
      list.push({ frame: frame.i, x, y });
      paths.set(t.id, list);
    }
  }
  return paths;
}

export function detectionCounts(data: TracksPayload): { t: number; count: number }[] {
  return data.frames.map((f) => ({
    t: f.i / (data.meta.fps || 30),
    count: f.tracks.length,
  }));
}

export function frameIndexForTime(currentTime: number, fps: number, frameCount: number): number {
  if (frameCount <= 0) return 0;
  const raw = Math.floor(currentTime * fps);
  return Math.min(Math.max(raw, 0), frameCount - 1);
}

export function totalDetections(data: TracksPayload): number {
  return data.frames.reduce((n, f) => n + f.tracks.length, 0);
}

export function frameByIndex(data: TracksPayload, frameIndex: number): FrameTracks | undefined {
  if (frameIndex < 0 || frameIndex >= data.frames.length) return undefined;
  const direct = data.frames[frameIndex];
  if (direct?.i === frameIndex) return direct;
  return data.frames.find((f) => f.i === frameIndex);
}

export function colorForId(id: number): string {
  const hue = (id * 47) % 360;
  return `hsl(${hue} 85% 52%)`;
}

/** Per-track time on screen in seconds, sorted by descending time. */
export function timeOnScreen(
  data: TracksPayload
): { id: number; frames: number; seconds: number }[] {
  const fps = data.meta.fps || 30;
  const counts = new Map<number, number>();
  for (const frame of data.frames) {
    for (const t of frame.tracks) {
      counts.set(t.id, (counts.get(t.id) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([id, frames]) => ({ id, frames, seconds: frames / fps }))
    .sort((a, b) => b.seconds - a.seconds);
}
