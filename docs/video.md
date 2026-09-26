# Video input

- Local llama.cpp: the Router forwards video attachments unchanged. llama.cpp
  itself decodes and samples the video. Its process must be able to launch
  FFmpeg and FFprobe, and a video-capable model/projector is required.
  Separate audio attachments are preserved and require an audio-capable model.
- OpenAI: decodes uploaded base64 videos locally, replacing each video with
  timestamped JPEG frames at its original position. Maximum 1 FPS, 32 frames
  per video (spread over the full duration for longer clips), 768 pixels per
  edge, 100 MiB per video. Requires a vision-capable model. Both Chat Completions
  and Responses receive images. Frames are sent to OpenAI; only decoding is local.
- No video audio extraction, transcription or extra model calls are performed.
  Each expanded video explicitly tells the model that audio was not processed.

Install `ffmpeg` and `ffprobe` on PATH, or set `FFMPEG_DIR` in the Router `.env`
to the directory containing both programs. The Router Docker image includes them.
The OpenAI adapter accepts `input_video.data` (raw base64 or data URL) and
`video_url.url`/`input_video.url` (base64 video data URL). It does not download
remote URLs or open paths provided by clients. Decoder children stop on cancellation
or a 60-second per-command timeout; temporary input and frames are then removed.

OpenRouter separately documents native video as
`{"type":"video_url","video_url":{"url":"data:video/mp4;base64,..."}}`.
That requires a video-capable upstream model/provider and is a cloud route.
The OpenRouter adapter translates Hub's `input_video` contract to this format.

OpenAI audio attachments require a supported Chat Completions audio model
(`gpt-audio`, `gpt-audio-mini`, `gpt-audio-1.5`, or `gpt-4o[-mini]-audio-preview`,
including dated snapshots). Other model IDs are rejected before video processing
or an API request. Audio is neither dropped nor automatically transcribed.

Sources:
- https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- https://developers.openai.com/api/docs/guides/images-vision
- https://openrouter.ai/docs/guides/overview/multimodal/videos
