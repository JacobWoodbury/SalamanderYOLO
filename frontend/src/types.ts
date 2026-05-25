export type TrackBox = {
  id: number;
  xyxy: [number, number, number, number];
  conf: number;
};

export type FrameTracks = {
  i: number;
  tracks: TrackBox[];
};

export type TracksPayload = {
  meta: {
    fps: number;
    width: number;
    height: number;
    frame_count: number;
    frame_count_cv?: number;
    model_path: string;
  };
  frames: FrameTracks[];
};

export type JobStatusResponse = {
  status: "pending" | "running" | "done" | "error";
  percent?: number;
  error?: string;
  meta?: TracksPayload["meta"];
};
