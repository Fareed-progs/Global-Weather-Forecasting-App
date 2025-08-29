import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# -----------------------------
# Constants
# -----------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# -----------------------------
# Helpers
# -----------------------------
@st.cache_data(show_spinner=False)
def geocode_location(query: str):
    """
    Use Nominatim (OpenStreetMap) to turn a free-text location into lat, lon and display name.
    No API key required. Respect Nominatim usage policy: do not flood requests.
    """
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    headers = {
        "User-Agent": "streamlit-weather-app/1.0 (+https://example.com)"
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
            display_name = item.get("display_name", query)
            return {"lat": lat, "lon": lon, "name": display_name}
        return None
    except requests.RequestException:
        return None

@st.cache_data(show_spinner=False)
def fetch_weather(lat: float, lon: float, days: int = 7):
    """
    Fetch weather from Open-Meteo.
    Returns current weather + daily forecast for `days` days.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone": "auto",
        "forecast_days": days,
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None

def weathercode_to_text(code: int):
    # Simple mapping for Open-Meteo weathercodes (not exhaustive)
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Drizzle: Light",
        53: "Drizzle: Moderate",
        55: "Drizzle: Dense",
        61: "Rain: Slight",
        63: "Rain: Moderate",
        65: "Rain: Heavy",
        71: "Snow fall: Slight",
        73: "Snow fall: Moderate",
        75: "Snow fall: Heavy",
        80: "Rain showers: Slight",
        81: "Rain showers: Moderate",
        82: "Rain showers: Violent",
        95: "Thunderstorm: Moderate",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return mapping.get(code, "Unknown")

def make_daily_dataframe(daily_json):
    if not daily_json:
        return None
    dates = daily_json.get("time", [])
    tmax = daily_json.get("temperature_2m_max", [])
    tmin = daily_json.get("temperature_2m_min", [])
    precip = daily_json.get("precipitation_sum", [])
    wcode = daily_json.get("weathercode", [])
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d,
            "tmax": tmax[i] if i < len(tmax) else None,
            "tmin": tmin[i] if i < len(tmin) else None,
            "precip_mm": precip[i] if i < len(precip) else None,
            "weather_text": weathercode_to_text(wcode[i]) if i < len(wcode) else None
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="🌐 Global Weather Forecast", layout="centered")
st.title("🌐 Global Weather Forecasting App (Free APIs)")
st.write(
    "This app uses **Nominatim (OpenStreetMap)** for geocoding and **Open-Meteo** for weather — both are free and require no API keys."
)

with st.form("location_form"):
    location_input = st.text_input("Enter a location (city, city,country, or country):", placeholder="e.g. Karachi, Pakistan  or  New York, US  or  Tokyo")
    forecast_days = st.selectbox("Forecast days", options=[3, 5, 7, 10], index=2)
    submit = st.form_submit_button("Get Forecast")

if submit:
    q = (location_input or "").strip()
    if q == "":
        st.info("Please enter a city or location.")
    else:
        with st.spinner("Resolving location..."):
            loc = geocode_location(q)
        if not loc:
            st.error("Location not found. Try a different query (e.g., 'Lahore', 'Lahore, PK', 'Pakistan').")
        else:
            lat = loc["lat"]
            lon = loc["lon"]
            pretty = loc["name"]
            st.success(f"Location: **{pretty}** — lat: {lat:.4f}, lon: {lon:.4f}")

            with st.spinner("Fetching weather data..."):
                data = fetch_weather(lat, lon, days=forecast_days)
            if not data:
                st.error("Failed to fetch weather data from Open-Meteo. Try again later.")
            else:
                # Current weather
                current = data.get("current_weather", {})
                if current:
                    st.subheader("Current Weather")
                    temp = current.get("temperature")
                    wind = current.get("windspeed")
                    wind_dir = current.get("winddirection")
                    time_iso = current.get("time")
                    time_local = time_iso
                    st.markdown(f"**Temperature:** {temp} °C  \n**Wind:** {wind} m/s  \n**Wind dir:** {wind_dir}°  \n**As of:** {time_local}")
                else:
                    st.info("No current weather block available for this location.")

                # Daily forecast
                daily = data.get("daily", {})
                df = make_daily_dataframe(daily)
                if df is None or df.empty:
                    st.info("No daily forecast available.")
                else:
                    st.subheader(f"{len(df)}-day Forecast")
                    # show table
                    display_df = df.copy()
                    display_df["date"] = display_df["date"].dt.date
                    st.dataframe(display_df.rename(columns={
                        "date": "Date",
                        "tmax": "Max (°C)",
                        "tmin": "Min (°C)",
                        "precip_mm": "Precip (mm)",
                        "weather_text": "Condition"
                    }), height=240)

                    # Chart: Tmax / Tmin line chart
                    chart_df = df.set_index("date")[["tmax", "tmin"]]
                    st.line_chart(chart_df)

                    # Precipitation bar chart
                    if df["precip_mm"].notnull().any():
                        st.bar_chart(df.set_index("date")["precip_mm"])

                    # More details per day (expanders)
                    for _, row in df.iterrows():
                        dstr = row["date"].date().isoformat()
                        with st.expander(f"{dstr} — {row['weather_text']}"):
                            st.write(f"Max: {row['tmax']} °C")
                            st.write(f"Min: {row['tmin']} °C")
                            st.write(f"Precipitation (sum): {row['precip_mm']} mm")

            st.markdown("---")
            st.caption("APIs: Nominatim (OpenStreetMap) & Open-Meteo. Use responsibly and avoid high-frequency automated requests.")
else:
    st.info("Type a location and press **Get Forecast** to see the weather.")
