import pytest
import json
from unittest.mock import patch, MagicMock
import sys
import os

# Add lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda'))

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

@patch('lambda_function.Client')
@patch('lambda_function.boto3.client')
def test_find_and_process_scene(mock_boto3, mock_client):
    """Test scene finding and processing logic"""
    # Mock STAC client
    mock_api = MagicMock()
    mock_client.open.return_value = mock_api
    
    # Mock search results
    mock_item = MagicMock()
    mock_item.id = 'test_scene'
    mock_item.properties = {'eo:cloud_cover': 5.0}
    mock_api.search.return_value.items.return_value = [mock_item]
    
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_boto3.return_value = mock_s3
    
    # This would test the actual processing logic
    # Add more specific tests based on your lambda function structure

def test_aoi_loading():
    """Test AOI configuration loading"""
    aoi_path = os.path.join(os.path.dirname(__file__), '..', 'lambda', 'aoi.geojson')
    
    if os.path.exists(aoi_path):
        with open(aoi_path) as f:
            aoi_data = json.load(f)
        
        assert 'type' in aoi_data
        assert aoi_data['type'] == 'FeatureCollection'
        assert 'features' in aoi_data
        assert len(aoi_data['features']) > 0

if __name__ == "__main__":
    pytest.main([__file__])
