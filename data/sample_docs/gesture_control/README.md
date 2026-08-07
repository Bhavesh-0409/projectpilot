# Gesture System Control

## What it is

A Python application that lets a user control their computer's system
volume and screen brightness using hand gestures captured through a
webcam, built with OpenCV and MediaPipe. The goal was to go beyond a
simple hand-detection demo and build something that reliably drives real
OS-level controls in real time.

## How it works

Each webcam frame is processed through MediaPipe's hand landmark model to
detect one hand and count extended fingers. The raw finger count is noisy
frame-to-frame, so the system smooths the reading over a short history
window before treating it as a stable gesture. Once a gesture is
confirmed, the corresponding system action (volume or brightness change)
is executed on a background worker thread, so the video feed and on-screen
UI stay responsive rather than freezing while the OS call happens.

## Gesture mapping

- Closed fist (0 fingers): mute system volume
- 1 finger: set screen brightness to low (30%)
- 2 fingers: set screen brightness to high (80%)
- 3 fingers: set system volume to low (20%)
- 4 fingers: set system volume to medium (50%)
- 5 fingers: set system volume to high (100%)

## Design decisions

Early versions suffered from gesture flickering — a single hand position
could be misread as different finger counts across consecutive frames,
causing the system to flicker between actions. Rather than adding more
model complexity to solve this, the fix was engineering-focused: temporal
smoothing across a frame window, cooldown logic between triggered actions,
and a simple, unambiguous gesture-to-action mapping. This made the system
noticeably more usable in practice than the earlier ML-heavy approach
would have been.

## Tech stack

- Python 3.9
- OpenCV (video capture and on-screen overlay)
- MediaPipe Hands (hand landmark detection)
- pycaw (Windows system audio control)
- screen-brightness-control (screen brightness control)

## Requirements and constraints

Requires Python 3.6+ and the libraries above. Designed specifically for
Windows, since it relies on `pycaw` for audio control. Performs best with
good lighting and a single hand clearly visible to the webcam.

## Out of scope

This is a single-purpose control utility — it does not attempt multi-hand
gestures, custom/configurable gesture mapping, cross-platform support, or
any control beyond volume and brightness.
