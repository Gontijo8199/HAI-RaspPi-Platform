---
type: subsystem
summary: On-demand webcam capture (open, warm up, 1 frame, close) returning CapturedImage JPEG
entry_points:
  - vision/camera.py
  - vision/image.py
covers:
  - vision/**
last_commit: 4d1d2e3
---

- LiveCamera (CameraCapture.live()) is the one exception to open-on-demand: it keeps the device open between open() and close() for previews, so capture() on the same device fails while it's open. Callers must close() in a finally (trainer's preview task does; cancelling it in exit() closes the camera). On the dev webcam, read() paces at ~10 fps at 1280x720 MJPG, so the trainer paces to 10 fps instead of sleeping a fixed interval. <!-- id:746a -->
