import argparse
import random
import signal
import sys
import time

import requests


DEFAULT_URL = "http://localhost:8000"
START_LAT = 36.8065
START_LNG = 10.1815


class DriverSimulator:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {"x-token": token}
        self.lat = START_LAT
        self.lng = START_LNG
        self.heading = 20.0
        self.running = True

    def set_online(self, online: bool):
        try:
            response = requests.post(
                f"{self.base_url}/status",
                json={"online": online},
                headers=self.headers,
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Status update failed: {exc}", file=sys.stderr)

    def send_location(self):
        noise_lat = random.uniform(-0.00018, 0.00018)
        noise_lng = random.uniform(-0.00018, 0.00018)

        speed_mps = 30.0 / 3.6
        self.heading = (self.heading + random.uniform(-12, 12)) % 360

        rad = self.heading * 3.141592653589793 / 180.0
        distance_km = (speed_mps * 3) / 1000.0
        distance_deg_lat = distance_km / 111.32
        distance_deg_lng = distance_km / (111.32 * max(abs(__import__('math').cos(self.lat * 3.141592653589793 / 180.0)), 0.0001))

        self.lat += distance_deg_lat * __import__('math').cos(rad)
        self.lng += distance_deg_lng * __import__('math').sin(rad)

        self.lat += noise_lat
        self.lng += noise_lng

        payload = {
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "speed": round(speed_mps, 2),
            "heading": round(self.heading, 2),
            "accuracy": round(random.uniform(10, 20), 2),
            "recorded_at": int(time.time()),
        }

        try:
            response = requests.post(
                f"{self.base_url}/location",
                json=payload,
                headers=self.headers,
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Location update failed: {exc}", file=sys.stderr)

    def run(self):
        self.set_online(True)
        print(f"Driver simulator started for token: {self.token}")

        while self.running:
            self.send_location()
            time.sleep(3)

    def stop(self):
        self.running = False
        self.set_online(False)
        print("Driver simulator stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(description="Simulate a Tunis taxi driver sending GPS locations.")
    parser.add_argument("--token", required=True, help="Driver token from /admin/drivers")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Backend URL (default: {DEFAULT_URL})")
    args = parser.parse_args()

    simulator = DriverSimulator(args.token, args.url)

    def handle_sigint(signum, frame):
        simulator.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        simulator.run()
    except KeyboardInterrupt:
        simulator.stop()


if __name__ == "__main__":
    main()
