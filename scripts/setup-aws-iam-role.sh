#!/bin/bash

# UAE Agriculture Monitoring - IAM Role Setup
# Run this script to create the Lambda execution role

set -e

# Configuration
ROLE_NAME="lambda-agriculture-role"
TRUST_POLICY_FILE="infrastructure/trust-policy.json"
S3_POLICY_FILE="infrastructure/lambda-s3-policy.json"
S3_POLICY_NAME="UAE-Agriculture-S3-Policy"

echo "🚀 Setting up IAM role for UAE Agriculture Monitoring..."

# Check if files exist
if [ ! -f "$TRUST_POLICY_FILE" ]; then
    echo "❌ Trust policy file not found: $TRUST_POLICY_FILE"
    exit 1
fi

if [ ! -f "$S3_POLICY_FILE" ]; then
    echo "❌ S3 policy file not found: $S3_POLICY_FILE"
    exit 1
fi

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📋 AWS Account ID: $ACCOUNT_ID"

# Create IAM role
echo "👤 Creating IAM role: $ROLE_NAME"
aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document file://$TRUST_POLICY_FILE \
    --description "Lambda execution role for UAE Agriculture Monitoring" || echo "Role may already exist"

# Attach AWS managed policy for basic Lambda execution
echo "🔗 Attaching basic Lambda execution policy..."
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create custom S3 policy
echo "📝 Creating custom S3 policy..."
aws iam create-policy \
    --policy-name $S3_POLICY_NAME \
    --policy-document file://$S3_POLICY_FILE \
    --description "S3 access policy for UAE Agriculture Monitoring" || echo "Policy may already exist"

# Attach custom S3 policy
echo "🔗 Attaching S3 policy to role..."
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/$S3_POLICY_NAME

echo "✅ IAM role setup complete!"
echo ""
echo "📋 Summary:"
echo "   Role Name: $ROLE_NAME"
echo "   Role ARN: arn:aws:iam::${ACCOUNT_ID}:role/$ROLE_NAME"
echo "   Custom Policy: $S3_POLICY_NAME"
echo ""
echo "🎯 Next steps:"
echo "   1. Wait 60 seconds for IAM propagation"
echo "   2. Deploy your Lambda function using GitHub Actions"
echo "   3. The role ARN will be: arn:aws:iam::${ACCOUNT_ID}:role/$ROLE_NAME"
