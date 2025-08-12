import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
import numpy as np
from io import BytesIO

# Add lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda_function'))

import lambda_function

def test_lambda_handler_test_mode():
    """Test lambda handler in test mode"""
    event = {
        'test_mode': True,
        'start_date': '2024-07-01',
        'end_date': '2024-07-31'
    }
    
    result = lambda_function.lambda_handler(event, None)
    
    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body['test_passed'] is True
    assert 'GitHub Actions Deployed' in body['version']
    print("✅ Test mode validation passed")

def test_aoi_loading():
    """Test AOI configuration loading"""
    aoi_path = os.path.join(os.path.dirname(__file__), '..', 'lambda_function', 'aoi.geojson')
    
    if os.path.exists(aoi_path):
        with open(aoi_path) as f:
            aoi_data = json.load(f)
        
        assert 'type' in aoi_data
        assert aoi_data['type'] == 'FeatureCollection'
        assert 'features' in aoi_data
        assert len(aoi_data['features']) > 0
        
        # Test geometry structure
        feature = aoi_data['features'][0]
        assert 'geometry' in feature
        assert 'coordinates' in feature['geometry']
        assert feature['geometry']['type'] == 'Polygon'
        print("✅ AOI GeoJSON validation passed")

@patch('lambda_function.Client')
@patch('lambda_function.boto3.client')
def test_find_and_process_scene_success(mock_boto3, mock_client):
    """Test successful scene finding and processing logic"""
    
    # Mock STAC client
    mock_api = MagicMock()
    mock_client.open.return_value = mock_api
    
    # Mock search results
    mock_item = MagicMock()
    mock_item.id = 'test_scene_12345'
    mock_item.properties = {
        'eo:cloud_cover': 5.0,
        'datetime': '2024-07-15T10:30:00Z'
    }
    mock_item.assets = {
        'red': MagicMock(href='http://test.com/red.tif'),
        'nir': MagicMock(href='http://test.com/nir.tif'),
        'green': MagicMock(href='http://test.com/green.tif'),
        'blue': MagicMock(href='http://test.com/blue.tif')
    }
    mock_api.search.return_value.items.return_value = [mock_item]
    
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_boto3.return_value = mock_s3
    
    # Mock successful processing
    with patch('lambda_function.process_scene_data') as mock_process:
        mock_process.return_value = {
            'scene_id': 'test_scene_12345',
            'scene_date': '2024-07-15',
            'processed_indices': ['NDVI', 'EVI'],
            'processing_summary': {'vegetation_health': 'Good'}
        }
        
        result = lambda_function.find_and_process_scene('2024-07-01', '2024-07-31')
        
        # Verify the scene was selected correctly
        assert result['scene_id'] == 'test_scene_12345'
        assert result['scene_date'] == '2024-07-15'
        assert 'NDVI' in result['processed_indices']
        
        # Verify STAC API was called
        mock_api.search.assert_called_once()
        search_call = mock_api.search.call_args
        assert 'datetime' in search_call.kwargs
        assert search_call.kwargs['datetime'] == '2024-07-01/2024-07-31'
        
        print("✅ Scene finding and processing test passed")

@patch('lambda_function.Client')
def test_find_and_process_scene_no_scenes_found(mock_client):
    """Test behavior when no suitable scenes are found"""
    
    # Mock STAC client with no results
    mock_api = MagicMock()
    mock_client.open.return_value = mock_api
    mock_api.search.return_value.items.return_value = []
    
    # Should raise exception when no scenes found
    with pytest.raises(Exception, match="No suitable scenes found"):
        lambda_function.find_and_process_scene('2024-07-01', '2024-07-31')
    
    print("✅ No scenes found error handling test passed")

def test_calculate_vegetation_indices():
    """Test NDVI and other vegetation index calculations"""
    
    # Create mock raster data as actual numpy arrays (not MagicMock objects)
    red_data = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    nir_data = np.array([[0.5, 0.6], [0.7, 0.8]], dtype=np.float32)
    green_data = np.array([[0.15, 0.25], [0.35, 0.45]], dtype=np.float32)
    blue_data = np.array([[0.05, 0.15], [0.25, 0.35]], dtype=np.float32)
    
    with patch('rasterio.open') as mock_rasterio:
        # Create context manager mocks that return actual numpy arrays
        def create_band_mock(data):
            mock_band = MagicMock()
            mock_band.__enter__ = MagicMock(return_value=mock_band)
            mock_band.__exit__ = MagicMock(return_value=None)
            mock_band.read.return_value = (data * 10000).astype(np.uint16)  # Sentinel-2 scaling
            mock_band.profile = {'dtype': 'uint16', 'nodata': 0, 'count': 1}
            return mock_band
        
        # Set up the context manager returns with actual data
        mock_rasterio.side_effect = [
            create_band_mock(red_data),
            create_band_mock(nir_data), 
            create_band_mock(green_data),
            create_band_mock(blue_data)
        ]
        
        # Mock file paths
        clipped_bands = {
            'red': '/tmp/red_clipped.tif',
            'nir': '/tmp/nir_clipped.tif',
            'green': '/tmp/green_clipped.tif',
            'blue': '/tmp/blue_clipped.tif'
        }
        
        with patch('pathlib.Path'):
            indices = lambda_function.calculate_vegetation_indices(clipped_bands, '/tmp')
            
            # Verify NDVI calculation
            assert 'NDVI' in indices
            calculated_ndvi = indices['NDVI']
            
            # Check NDVI values are reasonable (between -1 and 1)
            valid_ndvi = calculated_ndvi[~np.isnan(calculated_ndvi)]
            assert np.all(valid_ndvi >= -1.0)
            assert np.all(valid_ndvi <= 1.0)
            
            # Verify other indices exist
            assert 'EVI' in indices
            assert 'NDWI' in indices
            
            print("✅ Vegetation indices calculation test passed")

@patch('lambda_function.boto3.client')
def test_upload_results_to_s3(mock_boto3):
    """Test S3 upload functionality"""
    
    mock_s3 = MagicMock()
    mock_boto3.return_value = mock_s3
    
    # Mock existing time series
    mock_s3.get_object.return_value = {
        'Body': MagicMock(read=lambda: json.dumps({'scenes': []}).encode())
    }
    
    test_results = {
        'scene_id': 'test_scene',
        'scene_date': '2024-07-15',
        'statistics': {
            'NDVI': {'mean': 0.5, 'std': 0.1}
        },
        'summary': {'vegetation_health': 'Good'}
    }
    
    s3_paths = lambda_function.upload_results_to_s3(test_results, 'test_scene', '2024-07-15')
    
    # Verify S3 operations
    assert mock_s3.put_object.call_count >= 2  # Statistics + time series update
    
    # Check statistics upload
    stats_call = mock_s3.put_object.call_args_list[0]
    assert 'results/statistics/' in stats_call.kwargs['Key']
    assert stats_call.kwargs['ContentType'] == 'application/json'
    
    # Verify return value
    assert len(s3_paths) > 0
    assert all(path.startswith('s3://') for path in s3_paths)
    
    print("✅ S3 upload functionality test passed")

def test_lambda_handler_error_handling():
    """Test lambda handler error handling"""
    
    event = {
        'start_date': '2024-07-01',
        'end_date': '2024-07-31'
    }
    
    with patch('lambda_function.find_and_process_scene') as mock_process:
        # Mock an exception during processing
        mock_process.side_effect = Exception("Test error")
        
        result = lambda_function.lambda_handler(event, None)
        
        # Should return error response
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert 'error' in body
        assert 'Test error' in body['error']
        
        print("✅ Error handling test passed")

@patch('lambda_function.requests.get')
def test_download_bands_to_tmp(mock_requests):
    """Test band downloading functionality"""
    
    # Mock successful HTTP response
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.iter_content.return_value = [b'mock_data_chunk1', b'mock_data_chunk2']
    mock_requests.return_value = mock_response
    
    # Mock scene item
    mock_scene = MagicMock()
    mock_scene.assets = {
        'red': MagicMock(href='http://test.com/red.tif'),
        'nir': MagicMock(href='http://test.com/nir.tif')  # ✅ FIXED TYPO
    }
    
    with patch('pathlib.Path') as mock_path:
        mock_temp_path = MagicMock()
        mock_file = MagicMK()
        mock_file.stat.return_value.st_size = 1024 * 1024  # 1MB
        mock_temp_path.__truediv__.return_value = mock_file
        
        with patch('builtins.open', mock_open()) as mock_file_open:
            downloaded = lambda_function.download_bands_to_tmp(mock_scene, mock_temp_path)
            
            # Verify downloads
            assert 'red' in downloaded
            assert 'nir' in downloaded
            
            # Verify HTTP requests were made
            assert mock_requests.call_count == 2
            
            print("✅ Band download test passed")

def test_environment_variables():
    """Test environment variable handling"""
    
    # Test default values
    assert hasattr(lambda_function, 'S3_BUCKET')
    assert hasattr(lambda_function, 'AWS_REGION')
    
    # Test that environment variables are used
    with patch.dict(os.environ, {'S3_BUCKET': 'test-bucket', 'AWS_REGION': 'test-region'}):
        # Reload the module to pick up new env vars
        import importlib
        importlib.reload(lambda_function)
        
        assert lambda_function.S3_BUCKET == 'test-bucket'
        assert lambda_function.AWS_REGION == 'test-region'
        
        print("✅ Environment variables test passed")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
