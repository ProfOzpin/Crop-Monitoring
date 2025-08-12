import json
import boto3
import requests
import rasterio
import numpy as np
from pathlib import Path
from pystac_client import Client
from rasterio.mask import mask
import geopandas as gpd
from shapely.geometry import shape, mapping
import tempfile
import os
from datetime import datetime

# AWS Configuration from environment variables
S3_BUCKET = os.environ.get('S3_BUCKET', 'uae-agri-monitoring')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Load AOI from deployed file or use fallback
def load_aoi():
    """Load AOI from deployed config file or fallback to default"""
    default_aoi = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[55.74, 24.20], [55.75, 24.20], [55.75, 24.21], [55.74, 24.21], [55.74, 24.20]]]
            }
        }]
    }
    
    aoi_path = '/var/task/aoi.geojson'
    try:
        if os.path.exists(aoi_path):
            with open(aoi_path, 'r') as f:
                aoi = json.load(f)
            print("✓ Loaded AOI from deployed file")
            return aoi
    except Exception as e:
        print(f"Warning: Could not load AOI file: {e}")
    
    print("Using default AOI")
    return default_aoi

AOI_GEOJSON = load_aoi()
STAC_API_URL = "https://earth-search.aws.element84.com/v1"
SENTINEL_COLLECTION = 'sentinel-2-l2a'

def lambda_handler(event, context):
    """
    AWS Lambda function to process Sentinel-2 scenes on-demand
    Triggered by: Manual invoke, EventBridge schedule, or API Gateway
    """
    
    print(f"🚀 Starting satellite processing at {datetime.now()}")
    print(f"Event: {json.dumps(event, default=str)}")
    
    # Handle test mode for CI/CD deployment testing
    if event.get('test_mode', False):
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'CI/CD test passed - Lambda deployed successfully',
                'test_passed': True,
                'timestamp': datetime.now().isoformat(),
                'version': 'GitHub Actions Deployed',
                'environment': {
                    's3_bucket': S3_BUCKET,
                    'aws_region': AWS_REGION
                }
            })
        }
    
    try:
        # Get parameters from event
        scene_id = event.get('scene_id')
        start_date = event.get('start_date', '2024-07-01')
        end_date = event.get('end_date', '2024-07-31')
        
        if scene_id:
            # Process specific scene
            result = process_single_scene(scene_id)
        else:
            # Find and process best available scene
            result = find_and_process_scene(start_date, end_date)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Processing completed successfully',
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Processing failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }

def process_single_scene(scene_id):
    """Process a specific scene by ID"""
    # You would need to implement scene lookup by ID
    # For now, use the search approach
    raise NotImplementedError("Direct scene ID processing not implemented")

def find_and_process_scene(start_date, end_date):
    """Find best available Sentinel-2 scene and process it"""
    
    print(f"🔍 Searching for scenes from {start_date} to {end_date}")
    
    # Open STAC client
    api = Client.open(STAC_API_URL)
    
    # Search for scenes
    search = api.search(
        intersects=AOI_GEOJSON['features'][0]['geometry'],
        datetime=f'{start_date}/{end_date}',
        collections=[SENTINEL_COLLECTION],
        query={'eo:cloud_cover': {'lt': 20}}
    )
    
    items = list(search.items())
    print(f"Found {len(items)} candidate scenes")
    
    if not items:
        raise Exception("No suitable scenes found")
    
    # Select scene with lowest cloud cover
    best_scene = min(items, key=lambda x: x.properties.get('eo:cloud_cover', 100))
    scene_id = best_scene.id
    cloud_cover = best_scene.properties.get('eo:cloud_cover', 0)
    
    print(f"📡 Selected scene: {scene_id} ({cloud_cover:.1f}% cloud)")
    
    return process_scene_data(best_scene)

def process_scene_data(scene_item):
    """Main processing logic - download, process, store results, cleanup"""
    
    scene_id = scene_item.id
    scene_date = scene_item.properties['datetime'][:10]
    
    print(f"🛰️  Processing scene: {scene_id}")
    
    # Create temporary directory in Lambda /tmp
    with tempfile.TemporaryDirectory(dir='/tmp') as temp_dir:
        temp_path = Path(temp_dir)
        
        # Step 1: Download bands to /tmp
        downloaded_bands = download_bands_to_tmp(scene_item, temp_path)
        
        # Step 2: Create small AOI for clipping (reduces size by 95%+)
        small_aoi = create_small_aoi()
        
        # Step 3: Clip all bands to tiny AOI immediately
        clipped_bands = clip_bands_to_aoi(downloaded_bands, small_aoi, temp_path)
        
        # Step 4: Calculate vegetation indices on clipped data
        indices = calculate_vegetation_indices(clipped_bands, temp_path)
        
        # Step 5: Generate statistics and thumbnail
        results = generate_lightweight_outputs(indices, scene_id, scene_date, temp_path)
        
        # Step 6: Upload only results to S3 (not raw data)
        s3_paths = upload_results_to_s3(results, scene_id, scene_date)
        
        # Step 7: /tmp automatically cleaned up when function ends
        
        return {
            'scene_id': scene_id,
            'scene_date': scene_date,
            'processed_indices': list(indices.keys()),
            's3_outputs': s3_paths,
            'processing_summary': results['summary']
        }

def download_bands_to_tmp(scene_item, temp_path):
    """Download only required bands to Lambda /tmp storage"""
    
    required_bands = ['red', 'green', 'blue', 'nir']
    downloaded_bands = {}
    
    print("⬇️  Downloading bands to /tmp...")
    
    for band_name in required_bands:
        if band_name in scene_item.assets:
            asset_url = scene_item.assets[band_name].href
            band_file = temp_path / f'{band_name}.tif'
            
            print(f"  Downloading {band_name}...")
            
            # Stream download (no local storage)
            response = requests.get(asset_url, stream=True, timeout=300)
            response.raise_for_status()
            
            with open(band_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            downloaded_bands[band_name] = str(band_file)
            print(f"  ✓ {band_name} downloaded ({band_file.stat().st_size / 1024 / 1024:.1f}MB)")
    
    return downloaded_bands

def create_small_aoi():
    """Create very small AOI around Al Ain area to minimize data size"""
    
    # Small AOI around Al Ain farms (1km x 1km area)
    small_aoi_geojson = {
        "type": "FeatureCollection", 
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [55.74200, 24.20500],  # SW corner
                    [55.74700, 24.20500],  # SE corner  
                    [55.74700, 24.21000],  # NE corner
                    [55.74200, 24.21000],  # NW corner
                    [55.74200, 24.20500]   # Close polygon
                ]]
            }
        }]
    }
    
    return gpd.GeoDataFrame.from_features(
        small_aoi_geojson['features'], 
        crs='EPSG:4326'
    )

def clip_bands_to_aoi(downloaded_bands, aoi_gdf, temp_path):
    """Clip all bands to small AOI to drastically reduce file sizes"""
    
    print("✂️  Clipping to small AOI...")
    clipped_bands = {}
    
    for band_name, band_path in downloaded_bands.items():
        clipped_file = temp_path / f'{band_name}_clipped.tif'
        
        with rasterio.open(band_path) as src:
            # Reproject AOI to match raster CRS
            aoi_reprojected = aoi_gdf.to_crs(src.crs)
            
            # Clip raster
            geom = [mapping(geom) for geom in aoi_reprojected.geometry]
            clipped_data, clipped_transform = mask(src, geom, crop=True, filled=False)
            
            # Write clipped raster
            profile = src.profile.copy()
            profile.update({
                'height': clipped_data.shape[1],
                'width': clipped_data.shape[2], 
                'transform': clipped_transform
            })
            
            with rasterio.open(clipped_file, 'w', **profile) as dst:
                dst.write(clipped_data)
            
            clipped_bands[band_name] = str(clipped_file)
            
            # Show size reduction
            original_size = Path(band_path).stat().st_size / 1024 / 1024
            clipped_size = clipped_file.stat().st_size / 1024 / 1024
            reduction = (1 - clipped_size / original_size) * 100
            
            print(f"  ✓ {band_name}: {original_size:.1f}MB → {clipped_size:.1f}MB ({reduction:.1f}% reduction)")
    
    return clipped_bands

def calculate_vegetation_indices(clipped_bands, temp_path):
    """Calculate NDVI, EVI, etc. on clipped data"""
    
    print("🌱 Calculating vegetation indices ...")
    from pathlib import Path
    if not isinstance(temp_path, Path):
        temp_path = Path(temp_path)
    
    indices = {}
    
    # Read clipped bands
    with rasterio.open(clipped_bands['red']) as red_src, \
         rasterio.open(clipped_bands['nir']) as nir_src, \
         rasterio.open(clipped_bands['green']) as green_src, \
         rasterio.open(clipped_bands['blue']) as blue_src:
        
        # Read and scale data
        red = red_src.read(1).astype('float32') / 10000.0
        nir = nir_src.read(1).astype('float32') / 10000.0
        green = green_src.read(1).astype('float32') / 10000.0
        blue = blue_src.read(1).astype('float32') / 10000.0
        
        # Handle no-data
        red = np.where((red <= 0) | (red > 1), np.nan, red)
        nir = np.where((nir <= 0) | (nir > 1), np.nan, nir)
        green = np.where((green <= 0) | (green > 1), np.nan, green)
        blue = np.where((blue <= 0) | (blue > 1), np.nan, blue)
        
        # Calculate indices
        indices['NDVI'] = np.where(
            (nir + red) > 0,
            (nir - red) / (nir + red),
            np.nan
        )
        
        indices['EVI'] = np.where(
            (nir + 6*red - 7.5*blue + 1) > 0,
            2.5 * ((nir - red) / (nir + 6*red - 7.5*blue + 1)),
            np.nan
        )
        
        indices['NDWI'] = np.where(
            (green + nir) > 0,
            (green - nir) / (green + nir),
            np.nan
        )
        
        # Save index files
        profile = red_src.profile.copy()
        profile.update({'dtype': 'float32', 'nodata': np.nan})
        
        for index_name, index_data in indices.items():
            index_file = temp_path / f'{index_name}.tif'
            
            with rasterio.open(index_file, 'w', **profile) as dst:
                dst.write(index_data.astype('float32'), 1)
            
            # Calculate statistics
            valid_data = index_data[~np.isnan(index_data)]
            if len(valid_data) > 0:
                print(f"  ✓ {index_name}: mean={valid_data.mean():.3f}, range=[{valid_data.min():.3f}, {valid_data.max():.3f}]")
    
    return indices

def generate_lightweight_outputs(indices, scene_id, scene_date, temp_path):
    """Generate small outputs: statistics, thumbnail, summary"""
    
    print("📊 Generating lightweight outputs...")
    
    results = {
        'scene_id': scene_id,
        'scene_date': scene_date,
        'statistics': {},
        'summary': {}
    }
    
    # Calculate statistics for each index
    for index_name, index_data in indices.items():
        valid_data = index_data[~np.isnan(index_data)]
        
        if len(valid_data) > 0:
            stats = {
                'mean': float(valid_data.mean()),
                'std': float(valid_data.std()),
                'min': float(valid_data.min()),
                'max': float(valid_data.max()),
                'count': len(valid_data),
                'vegetation_pixels': int(np.sum(valid_data > 0.3)) if index_name == 'NDVI' else None
            }
            results['statistics'][index_name] = stats
    
    # Generate summary
    ndvi_stats = results['statistics'].get('NDVI', {})
    results['summary'] = {
        'vegetation_health': 'Good' if ndvi_stats.get('mean', 0) > 0.3 else 'Poor',
        'vegetation_coverage': f"{(ndvi_stats.get('vegetation_pixels', 0) / ndvi_stats.get('count', 1)) * 100:.1f}%",
        'processing_timestamp': datetime.now().isoformat(),
        'data_size': 'Small AOI (1km²)'
    }
    
    return results

def upload_results_to_s3(results, scene_id, scene_date):
    """Upload only lightweight results to S3 (not raw data)"""
    
    print("☁️  Uploading results to S3...")
    
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    s3_paths = []
    
    # Upload statistics as JSON
    stats_key = f"results/statistics/{scene_date}/{scene_id}_stats.json"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=stats_key,
        Body=json.dumps(results, indent=2),
        ContentType='application/json'
    )
    s3_paths.append(f"s3://{S3_BUCKET}/{stats_key}")
    
    # Update time series log
    update_time_series_log(results, s3_client)
    
    print(f"  ✓ Results uploaded to S3: {len(s3_paths)} files")
    return s3_paths

def update_time_series_log(results, s3_client):
    """Maintain rolling time series of results"""
    
    log_key = "time_series/vegetation_log.json"
    
    try:
        # Get existing log
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=log_key)
        time_series = json.loads(response['Body'].read())
    except:
        # Create new log
        time_series = {'scenes': []}
    
    # Add new entry
    time_series['scenes'].append({
        'scene_id': results['scene_id'],
        'date': results['scene_date'],
        'ndvi_mean': results['statistics'].get('NDVI', {}).get('mean', 0),
        'vegetation_health': results['summary']['vegetation_health']
    })
    
    # Keep only last 20 scenes (rolling window)
    time_series['scenes'] = time_series['scenes'][-20:]
    time_series['last_updated'] = datetime.now().isoformat()
    
    # Upload updated log
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=log_key,
        Body=json.dumps(time_series, indent=2),
        ContentType='application/json'
    )

# For local testing (not part of Lambda)
def local_test():
    """Test function locally before deploying to Lambda"""
    
    event = {
        'test_mode': True
    }
    
    result = lambda_handler(event, None)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    local_test()
