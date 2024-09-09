import geopy.distance
import pandas as pd

df = pd.read_csv("~/Documents/development/projects/rhb-sensor-monitor/data-0828/positions_circle_20240829_04_05.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df_diff = df.diff()
df["timestamp_diff"] = df_diff["timestamp"]
for i in range(1, len(df)):
    df.loc[i, "lat_prev"] = df.loc[i - 1, 'lat']
    df.loc[i, "lon_prev"] = df.loc[i - 1, 'lon']
    coords_1 = (df.loc[i, "lat_prev"], df.loc[i, "lat_prev"])
    coords_2 = (df.loc[i, "lat"], df.loc[i, "lat"])
    df.loc[i, "distance"] = geopy.distance.geodesic(coords_1, coords_2).mi
    df.loc[i, "speed"] = df.loc[i, "distance"] / df.loc[i, "timestamp_diff"].seconds * 3600
df.to_csv("~/Documents/development/projects/rhb-sensor-monitor/data-0828/positions_speed_20240829_04_05.csv")
