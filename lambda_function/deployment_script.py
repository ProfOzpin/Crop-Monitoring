import boto3
import json
import zipfile
from pathlib import Path

def create_lambda_deployment_package():
    """Create deployment package for Lambda function"""
    
    print("📦 Creating Lambda deployment package...")
    
    # Create deployment zip
    with zipfile.ZipFile('satellite_processor.zip', 'w') as zip_file:
        zip_file.write('01_aws_satellite_processor.py', 'lambda_function.py')
        
        # Add requirements (you'll need to pip install these into a folder)
        # zip_file.write('dependencies/', arcname='')
    
    print("✓ Deployment package created: satellite_processor.zip")

def deploy_to_aws():
    """Deploy Lambda function to AWS"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Create or update Lambda function
    function_config = {
        'FunctionName': 'uae-satellite-processor',
        'Runtime': 'python3.10',
        'Role': 'arn:aws:iam::YOUR-ACCOUNT:role/lambda-execution-role',  # Update this
        'Handler': 'lambda_function.lambda_handler',
        'Timeout': 900,  # 15 minutes
        'MemorySize': 3008,  # Maximum memory for large raster processing
        'Environment': {
            'Variables': {
                'S3_BUCKET': 'uae-agri-monitoring'
            }
        }
    }
    
    # Upload function code
    with open('satellite_processor.zip', 'rb') as zip_file:
        function_config['Code'] = {'ZipFile': zip_file.read()}
    
    try:
        lambda_client.create_function(**function_config)
        print("✓ Lambda function created successfully")
    except lambda_client.exceptions.ResourceConflictException:
        # Update existing function
        lambda_client.update_function_code(
            FunctionName='uae-satellite-processor',
            ZipFile=function_config['Code']['ZipFile']
        )
        print("✓ Lambda function updated successfully")

def create_s3_bucket():
    """Create S3 bucket for storing results"""
    
    s3_client = boto3.client('s3', region_name='us-east-1')
    
    try:
        s3_client.create_bucket(Bucket='uae-agri-monitoring')
        print("✓ S3 bucket created: uae-agri-monitoring")
    except s3_client.exceptions.BucketAlreadyExists:
        print("✓ S3 bucket already exists")

if __name__ == "__main__":
    create_s3_bucket()
    create_lambda_deployment_package()
    # deploy_to_aws()  # Uncomment when ready
