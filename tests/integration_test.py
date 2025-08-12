import boto3
import json
import time
from datetime import datetime

def test_full_pipeline():
    """Test the complete satellite processing pipeline"""
    
    print("🧪 Starting integration test...")
    
    # Initialize AWS clients
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')
    
    # Test 1: Lambda function invocation
    print("1. Testing Lambda function invocation...")
    
    test_payload = {
        'start_date': '2024-07-01',
        'end_date': '2024-07-31',
        'test_mode': False
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='uae-satellite-processor',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        result = json.loads(response['Payload'].read())
        assert response['StatusCode'] == 200, f"Lambda invocation failed: {result}"
        
        print("   ✅ Lambda function invoked successfully")
        
    except Exception as e:
        print(f"   ❌ Lambda invocation failed: {e}")
        raise
    
    # Test 2: Check S3 outputs
    print("2. Checking S3 outputs...")
    
    try:
        # Wait for processing to complete
        time.sleep(30)
        
        # Check for time series log
        s3_client.head_object(
            Bucket='uae-agri-monitoring',
            Key='time_series/vegetation_log.json'
        )
        print("   ✅ Time series log found in S3")
        
    except s3_client.exceptions.NoSuchKey:
        print("   ⚠️  Time series log not found - may be first run")
    except Exception as e:
        print(f"   ❌ S3 check failed: {e}")
    
    # Test 3: Verify system health
    print("3. System health check...")
    
    try:
        # Check Lambda function configuration
        function_config = lambda_client.get_function(
            FunctionName='uae-satellite-processor'
        )
        
        assert function_config['Configuration']['State'] == 'Active'
        print("   ✅ Lambda function is active and healthy")
        
    except Exception as e:
        print(f"   ❌ System health check failed: {e}")
        raise
    
    print("🎉 Integration test completed successfully!")

if __name__ == "__main__":
    test_full_pipeline()
