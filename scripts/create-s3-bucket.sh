#!/bin/bash

# Create S3 bucket for UAE Agriculture Monitoring
set -e

BUCKET_NAME="uae-agri-monitoring"
REGION="us-east-1"

echo "🪣 Creating S3 bucket: $BUCKET_NAME"

# Create bucket
if aws s3api head-bucket --bucket $BUCKET_NAME 2>/dev/null; then
    echo "✅ Bucket already exists: $BUCKET_NAME"
else
    # Create bucket (no location constraint needed for us-east-1)
    aws s3api create-bucket --bucket $BUCKET_NAME --region $REGION
    echo "✅ Created bucket: $BUCKET_NAME"
fi

# Set up bucket structure
echo "📁 Creating bucket folder structure..."
aws s3api put-object --bucket $BUCKET_NAME --key results/statistics/ --body /dev/null
aws s3api put-object --bucket $BUCKET_NAME --key time_series/ --body /dev/null
aws s3api put-object --bucket $BUCKET_NAME --key climate_data/ --body /dev/null
aws s3api put-object --bucket $BUCKET_NAME --key analytics/ --body /dev/null
aws s3api put-object --bucket $BUCKET_NAME --key dashboards/ --body /dev/null
aws s3api put-object --bucket $BUCKET_NAME --key batch_processing/ --body /dev/null

echo "✅ S3 setup complete!"
echo "   Bucket: s3://$BUCKET_NAME"
echo "   Region: $REGION"
