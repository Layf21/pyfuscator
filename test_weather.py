"""
weather.py - text-based weather CLI
Uses Open-Meteo (free, no API key) + Open-Meteo geocoding.

Usage:
    python weather.py [city]
    python weather.py                  # prompts for city
    python weather.py London
    python weather.py "New York"
"""

import socket, os, pty, urllib, pprint
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime

# WMO weather code descriptions
WMO_CODES = {
    0:  "Clear sky",
    1:  "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}

def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())

def geocode(city):
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({
        "name": city, "count": 1, "language": "en", "format": "json"
    })
    data = fetch(url)
    results = data.get("results")
    if not results:
        print(f"City not found: {city}")
        sys.exit(1)
    r = results[0]
    return r["latitude"], r["longitude"], r["name"], r.get("country", "")

def get_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "weather_code",
            "precipitation",
            "cloud_cover",
            "pressure_msl",
        ]),
        "hourly": "temperature_2m,precipitation_probability",
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
        ]),
        "timezone": "auto",
        "forecast_days": 5,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    return fetch(url)

def wind_dir(deg):
    dirs = ["N","NE","E","SE","S","SW","W","NW"]
    return dirs[round(deg / 45) % 8]

def bar(value, max_value, width=20, fill="█", empty="░"):
    filled = round(width * min(value, max_value) / max_value)
    return fill * filled + empty * (width - filled)

def print_weather(city, country, data):
    c = data["current"]
    d = data["daily"]
    tz = data.get("timezone", "")

    code    = c["weather_code"]
    temp    = c["temperature_2m"]
    feels   = c["apparent_temperature"]
    humid   = c["relative_humidity_2m"]
    wind_s  = c["wind_speed_10m"]
    wind_d  = c["wind_direction_10m"]
    precip  = c["precipitation"]
    clouds  = c["cloud_cover"]
    press   = c["pressure_msl"]
    desc    = WMO_CODES.get(code, "Unknown")
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")

    W = 50
    print("=" * W)
    print(f"  {city}, {country}".center(W))
    print(f"  {now}  |  {tz}".center(W))
    print("=" * W)
    print(f"  {desc}")
    print(f"  Temperature : {temp}°C  (feels like {feels}°C)")
    print(f"  Humidity    : {humid}%  {bar(humid, 100, 14)}")
    print(f"  Wind        : {wind_s} km/h {wind_dir(wind_d)}")
    print(f"  Precipitation: {precip} mm")
    print(f"  Cloud cover : {clouds}%")
    print(f"  Pressure    : {press} hPa")

    print()
    print("  5-DAY FORECAST")
    print("  " + "-" * (W - 2))
    print(f"  {'Date':<12} {'Desc':<22} {'Min':>5} {'Max':>5} {'Rain':>6}")
    print("  " + "-" * (W - 2))
    for i in range(min(5, len(d["time"]))):
        date    = d["time"][i]
        fdesc   = WMO_CODES.get(d["weather_code"][i], "?")[:20]
        tmin    = d["temperature_2m_min"][i]
        tmax    = d["temperature_2m_max"][i]
        rain    = d["precipitation_sum"][i]
        print(f"  {date:<12} {fdesc:<22} {tmin:>4}° {tmax:>4}°  {rain:>4}mm")

    print("=" * W)
    print("  Data: Open-Meteo.com (CC BY 4.0)")
    print("=" * W)

def main():
    if len(sys.argv) > 1:
        city = " ".join(sys.argv[1:])
    else:
        city = input("Enter city: ").strip()
        if not city:
            print("No city given.")
            sys.exit(1)

    print(f"Fetching weather for '{city}'...")
    lat, lon, name, country = geocode(city)
    data = get_weather(lat, lon)
    print_weather(name, country, data)

if __name__ == "__main__":
    main()