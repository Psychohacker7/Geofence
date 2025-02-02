import shapely.geometry as geom
import shapely.ops as ops
from shapely.geometry.polygon import Polygon, LinearRing, Point
from shapely.geometry import LineString, MultiPolygon
import matplotlib.pyplot as plt
from shapely.ops import polygonize, linemerge
import numpy as np
from shapely.ops import unary_union

# Function to read waypoints from a file
def read_waypoints(filename):
    waypoints = []
    with open(filename, 'r') as file:
        for line in file:
            if line.startswith('QGC'):
                continue
            parts = line.strip().split('\t')
            lat = float(parts[8])
            lon = float(parts[9])
            waypoints.append((lon, lat))
    return waypoints

def meters_to_degrees(meters, latitude):
    # Values obtained from the internet
    meters_per_degree_latitude = 111045  # meters
    meters_per_degree_longitude = 87870.18  # meters at the equator
    
    # Convert latitude to radians for numpy trigonometric functions
    lat_radians = np.radians(latitude)
    
    # Calculate degrees of latitude
    degrees_latitude = meters / meters_per_degree_latitude
    
    # Calculate degrees of longitude, accounting for latitude. Could have done the opposite.
    degrees_longitude = meters / (meters_per_degree_longitude * np.cos(lat_radians))
    
    return degrees_latitude, degrees_longitude



def create_geofence(waypoints, buffer_distance_meters):
    # Create line segments from waypoints
    line_segments = []
    for i in range(len(waypoints) - 1):
        segment = LineString([waypoints[i], waypoints[i+1]])
        line_segments.append(segment)
    
    # Buffer each line segment separately
    buffered_segments = []
    for segment in line_segments:
        # Calculate average latitude for this segment
        avg_lat = np.mean([segment.coords[0][1], segment.coords[1][1]])
        # Convert buffer distance to degrees
        buffer_lat, buffer_lon = meters_to_degrees(buffer_distance_meters, avg_lat)
        # Use the larger of the two as the buffer distance
        buffer_distance_degrees = max(buffer_lat, buffer_lon)
        # Buffer might be slightly larger than specified in some directions, but never smaller.
        buffered_segments.append(segment.buffer(buffer_distance_degrees, resolution=4)) # res is segments per quarter circle, controls how smooth the curved parts of the buffer are.
    
    # Manually piece together buffered segments
    merged = linemerge([segment.exterior for segment in buffered_segments])
    polygons = list(polygonize(merged))

    # If there are multiple polygons, create a MultiPolygon
    geofence = MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]

    # Simplify the geofence geometry
    geofence = geofence.simplify(tolerance=buffer_distance_degrees / 2, preserve_topology=True)
    
    return geofence

def simplify_geofence(geofence, buffer_distance_meters, simplification_tolerance=0.0001):
    simplified_segments = []

    # Process each segment
    segments = geofence.geoms if isinstance(geofence, MultiPolygon) else [geofence]
    for segment in segments:
        # Buffer conversion
        avg_lat = np.mean([p[1] for p in segment.exterior.coords])
        buffer_lat, buffer_lon = meters_to_degrees(buffer_distance_meters, avg_lat)
        buffer_distance_degrees = max(buffer_lat, buffer_lon)

        # Simplify segment
        simplified = segment.simplify(simplification_tolerance, preserve_topology=True)
        simplified_segments.append(simplified)

    # Handle intersections and merge segments without unary_union
    merged_lines = linemerge([seg.exterior for seg in simplified_segments])
    
    if merged_lines.geom_type == 'LineString':
        final_geofence = Polygon(merged_lines)
    elif merged_lines.geom_type == 'MultiLineString':
        polygons = [Polygon(line) for line in merged_lines.geoms]
        final_geofence = MultiPolygon(polygons)
    else:
        raise ValueError("Unexpected geometry type after merging")

    # Final simplification
    simplified_geofence = final_geofence.simplify(simplification_tolerance, preserve_topology=True)

    return simplified_geofence

# Function to save the geofence to files
# To Mission Planner .poly file
def save_geofence_to_poly(geofence, filename):
    with open(filename, 'w') as file:
        file.write("#saved by Python Script\n")
        
        if isinstance(geofence, MultiPolygon):
            polygons = list(geofence.geoms)
        elif isinstance(geofence, Polygon):
            polygons = [geofence]
        else:
            raise ValueError("Geofence must be a Polygon or MultiPolygon")

        for polygon in polygons:
            coords = list(polygon.exterior.coords)
            for lon, lat in coords:  # Shapely uses (lon, lat) order
                file.write(f"{lat:.10f} {lon:.10f}\n")  # .poly format expects (lat, lon)
            
            # Ensure the polygon is closed by writing the first point again if necessary
            if coords[0] != coords[-1]:
                file.write(f"{coords[0][1]:.10f} {coords[0][0]:.10f}\n")
            
            # Add a separator between polygons if there are multiple
            if len(polygons) > 1:
                file.write("END\n")

        # Final END for the file
        file.write("END\n")
