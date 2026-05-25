import { useCallback, useEffect, useRef } from "react";
import type { FrameTracks, TracksPayload } from "../types";
import type { PathPoint } from "../lib/tracks";
import { colorForId, frameByIndex, frameIndexForTime } from "../lib/tracks";

type Props = {
  jobId: string;
  data: TracksPayload;
  paths: Map<number, PathPoint[]>;
  currentFrame: number;
  showTrail: boolean;
  onFrameChange?: (frame: number) => void;
};

export default function VideoPlayerOverlay({
  jobId,
  data,
  paths,
  currentFrame,
  showTrail,
  onFrameChange,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return;

    canvas.width = vw;
    canvas.height = vh;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, vw, vh);

    const frameData: FrameTracks | undefined = frameByIndex(data, currentFrame);

    if (showTrail) {
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.85;
      for (const [id, pts] of paths) {
        const visible = pts.filter((p) => p.frame <= currentFrame);
        if (visible.length < 2) continue;
        ctx.strokeStyle = colorForId(id);
        ctx.beginPath();
        ctx.moveTo(visible[0].x, visible[0].y);
        for (let i = 1; i < visible.length; i++) {
          ctx.lineTo(visible[i].x, visible[i].y);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    if (!frameData) return;

    for (const t of frameData.tracks) {
      const [x1, y1, x2, y2] = t.xyxy;
      const col = colorForId(t.id);
      ctx.strokeStyle = col;
      ctx.lineWidth = 3;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.fillStyle = col;
      ctx.font = "14px system-ui, sans-serif";
      const label = `ID ${t.id} ${(t.conf * 100).toFixed(0)}%`;
      ctx.fillText(label, x1, Math.max(16, y1 - 4));
    }
  }, [currentFrame, data.frames, paths, showTrail]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const fps = data.meta.fps || 30;
    const n = data.meta.frame_count;
    const emitFrame = () => {
      const idx = frameIndexForTime(v.currentTime, fps, n);
      onFrameChange?.(idx);
    };
    const onMeta = () => {
      draw();
      emitFrame();
    };
    const onTime = () => {
      draw();
      emitFrame();
    };
    const onSeek = () => {
      draw();
      emitFrame();
    };
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("seeked", onSeek);
    return () => {
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("seeked", onSeek);
    };
  }, [data.meta.fps, data.meta.frame_count, draw, onFrameChange]);

  useEffect(() => {
    draw();
  }, [draw]);

  const src = `/api/jobs/${jobId}/video`;

  return (
    <div className="video-wrap">
      <video ref={videoRef} src={src} controls playsInline />
      <canvas ref={canvasRef} />
    </div>
  );
}
