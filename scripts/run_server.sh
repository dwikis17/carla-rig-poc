#!/usr/bin/env bash
# Example CARLA server launch. Run this on the machine with the GPU, then start the client:
#   python -m carla_rig.main --config config/default.yaml
#
# Set CARLA_ROOT to your extracted CARLA package (the folder containing CarlaUE4.sh).
#
# Launcher names differ by build:
#   * CARLA 0.9.x (Unreal Engine 4):  ./CarlaUE4.sh        (Windows: CarlaUE4.exe)
#   * CARLA 0.10+ (Unreal Engine 5):  ./CarlaUnreal.sh     (Windows: CarlaUnreal.exe)
# Flags below are the same for both unless noted.
set -euo pipefail

CARLA_ROOT="${CARLA_ROOT:-$HOME/CARLA}"
PORT="${CARLA_PORT:-2000}"   # must match server.port in config/default.yaml

if [[ -x "$CARLA_ROOT/CarlaUnreal.sh" ]]; then
  LAUNCHER="$CARLA_ROOT/CarlaUnreal.sh"
else
  LAUNCHER="$CARLA_ROOT/CarlaUE4.sh"
fi

# Flags:
#   -RenderOffScreen       no server-side spectator window. Cameras STILL render (this is not
#                          no_rendering_mode); it just saves GPU and avoids a second window.
#                          Drop it if you want the free-fly spectator view for debugging.
#   -quality-level=Low     lower shading quality → much higher FPS. Use Epic for final visuals.
#   -carla-rpc-port=N      RPC port the client connects to (server.port). Streaming uses N+1, N+2.
#   -nosound               disable UE audio (CARLA has none worth hearing; avoids audio-device errors).
# Other useful flags:
#   -prefernvidia          pick the discrete GPU on multi-GPU laptops (Windows/UE4)
#   -ResX=1280 -ResY=720   size of the spectator window (when not off-screen)
exec "$LAUNCHER" \
  -RenderOffScreen \
  -quality-level=Low \
  -carla-rpc-port="$PORT" \
  -nosound
