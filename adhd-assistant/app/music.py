from typing import Dict, Any


class Music:
    def __init__(self):
        pass

    def play_track(self, track_name: str) -> Dict[str, Any]:
        print(f"🎵 [MÚSICA] Reproduciendo: {track_name}")
        return {
            "status": "ok",
            "message": f"Ahora suena: {track_name}",
            "action": "play_track",
        }