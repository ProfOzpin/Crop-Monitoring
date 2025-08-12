import boto3
import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from datetime import datetime
import requests
import seaborn as sns
from io import StringIO
import warnings
import sys

warnings.filterwarnings('ignore')

# AWS Configuration
S3_BUCKET = 'uae-agri-monitoring'
AWS_REGION = 'us-east-1'
LOCAL_CACHE_DIR = Path('aws_analysis_cache')

def setup_aws_clients():
    """Initialize AWS clients for S3 access"""
    print("🔧 Setting up AWS clients...")
    
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        lambda_client = boto3.client('lambda', region_name=AWS_REGION)
        
        # Test S3 connection
        s3_client.list_objects_v2(Bucket=S3_BUCKET, MaxKeys=1)
        print(f"✓ Connected to S3 bucket: {S3_BUCKET}")
        
        return s3_client, lambda_client
        
    except Exception as e:
        print(f"❌ AWS setup failed: {e}")
        print("Make sure you have:")
        print("1. AWS credentials configured (aws configure)")
        print("2. S3 bucket created: uae-agri-monitoring")
        print("3. Lambda function deployed from Step 1")
        return None, None

def trigger_scene_processing(lambda_client, scene_params):
    """Trigger Lambda processing for a specific scene"""
    
    print(f"🛰️  Triggering processing for scene...")
    
    try:
        response = lambda_client.invoke(
            FunctionName='uae-satellite-processor',
            InvocationType='RequestResponse',  # Synchronous
            Payload=json.dumps(scene_params)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            print("✓ Scene processing completed successfully")
            return json.loads(result['body'])
        else:
            print(f"❌ Processing failed: {result}")
            return None
            
    except Exception as e:
        print(f"❌ Lambda invocation failed: {e}")
        return None

def download_s3_results(s3_client, local_cache_dir):
    """Download lightweight results from S3 for analysis"""
    
    print("⬇️  Downloading analysis results from S3...")
    
    local_cache_dir.mkdir(exist_ok=True)
    downloaded_files = []
    
    try:
        # List all results in S3
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='results/'
        )
        
        if 'Contents' not in response:
            print("❌ No results found in S3. Run Step 1 processing first.")
            return []
        
        for obj in response['Contents']:
            s3_key = obj['Key']
            local_file = local_cache_dir / Path(s3_key).name
            
            print(f"  Downloading {s3_key}...")
            s3_client.download_file(S3_BUCKET, s3_key, str(local_file))
            downloaded_files.append(local_file)
            
            # Show file size (should be small)
            size_kb = obj['Size'] / 1024
            print(f"    ✓ {local_file.name} ({size_kb:.1f}KB)")
        
        print(f"✓ Downloaded {len(downloaded_files)} result files")
        return downloaded_files
        
    except Exception as e:
        print(f"❌ S3 download failed: {e}")
        return []

def load_time_series_data(s3_client):
    """Load time series vegetation data from S3"""
    
    print("📊 Loading time series data...")
    
    try:
        # Get the time series log
        response = s3_client.get_object(
            Bucket=S3_BUCKET,
            Key='time_series/vegetation_log.json'
        )
        
        time_series = json.loads(response['Body'].read())
        
        if 'scenes' in time_series and time_series['scenes']:
            df = pd.DataFrame(time_series['scenes'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            print(f"✓ Loaded {len(df)} processed scenes")
            print(f"Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
            
            return df
        else:
            print("❌ No time series data found")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"❌ Time series load failed: {e}")
        return pd.DataFrame()

def analyze_vegetation_trends(time_series_df):
    """Analyze vegetation trends from processed data"""
    
    if time_series_df.empty:
        print("❌ No data available for trend analysis")
        return {}
    
    print("🌱 Analyzing vegetation trends...")
    
    analysis = {}
    
    # Basic statistics
    analysis['total_scenes'] = len(time_series_df)
    analysis['date_range'] = {
        'start': time_series_df['date'].min().strftime('%Y-%m-%d'),
        'end': time_series_df['date'].max().strftime('%Y-%m-%d')
    }
    
    # NDVI statistics
    analysis['ndvi_stats'] = {
        'mean': float(time_series_df['ndvi_mean'].mean()),
        'min': float(time_series_df['ndvi_mean'].min()),
        'max': float(time_series_df['ndvi_mean'].max()),
        'std': float(time_series_df['ndvi_mean'].std())
    }
    
    # Vegetation health classification
    health_counts = time_series_df['vegetation_health'].value_counts()
    analysis['health_distribution'] = health_counts.to_dict()
    
    # Trend analysis (if enough data points)
    if len(time_series_df) >= 3:
        # Simple linear trend
        x = np.arange(len(time_series_df))
        y = time_series_df['ndvi_mean'].values
        trend_slope = np.polyfit(x, y, 1)[0]
        
        analysis['trend'] = {
            'slope': float(trend_slope),
            'direction': 'improving' if trend_slope > 0.001 else 'declining' if trend_slope < -0.001 else 'stable'
        }
    
    # Recent vs historical comparison
    if len(time_series_df) >= 6:
        recent_ndvi = time_series_df.tail(3)['ndvi_mean'].mean()
        historical_ndvi = time_series_df.head(3)['ndvi_mean'].mean()
        
        analysis['comparison'] = {
            'recent_ndvi': float(recent_ndvi),
            'historical_ndvi': float(historical_ndvi),
            'change': float(recent_ndvi - historical_ndvi)
        }
    
    print("✓ Vegetation trend analysis complete")
    return analysis

def create_aws_visualizations(time_series_df, analysis, output_dir):
    """Create visualizations from AWS-processed data"""
    
    if time_series_df.empty:
        print("❌ No data available for visualization")
        return
    
    print("📈 Creating visualizations...")
    
    output_dir.mkdir(exist_ok=True)
    
    # Set up the plotting style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Suppress GUI display for CI/CD environments
    plt.ioff()
    
    # Create comprehensive dashboard
    fig = plt.figure(figsize=(16, 12))
    
    # 1. NDVI Time Series
    ax1 = plt.subplot(2, 3, 1)
    plt.plot(time_series_df['date'], time_series_df['ndvi_mean'], 'o-', linewidth=2, markersize=6)
    plt.title('NDVI Time Series - Abu Dhabi AOI', fontsize=12, fontweight='bold')
    plt.ylabel('Mean NDVI')
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    
    # Add trend line if enough data
    if 'trend' in analysis:
        x_numeric = np.arange(len(time_series_df))
        trend_line = np.polyfit(x_numeric, time_series_df['ndvi_mean'], 1)
        plt.plot(time_series_df['date'], np.polyval(trend_line, x_numeric), '--', 
                color='red', alpha=0.7, label=f"Trend: {analysis['trend']['direction']}")
        plt.legend()
    
    # 2. Vegetation Health Distribution
    ax2 = plt.subplot(2, 3, 2)
    if 'health_distribution' in analysis:
        health_data = analysis['health_distribution']
        colors = ['green' if k == 'Good' else 'orange' for k in health_data.keys()]
        bars = plt.bar(health_data.keys(), health_data.values(), color=colors, alpha=0.7)
        plt.title('Vegetation Health Distribution', fontsize=12, fontweight='bold')
        plt.ylabel('Number of Scenes')
        
        # Add percentages on bars
        total = sum(health_data.values())
        for bar, value in zip(bars, health_data.values()):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                    f'{value}\n({value/total*100:.1f}%)', ha='center', va='bottom')
    
    # 3. NDVI Distribution Histogram
    ax3 = plt.subplot(2, 3, 3)
    plt.hist(time_series_df['ndvi_mean'], bins=10, alpha=0.7, color='green', edgecolor='black')
    plt.axvline(analysis['ndvi_stats']['mean'], color='red', linestyle='--', 
                label=f"Mean: {analysis['ndvi_stats']['mean']:.3f}")
    plt.title('NDVI Value Distribution', fontsize=12, fontweight='bold')
    plt.xlabel('NDVI Value')
    plt.ylabel('Frequency')
    plt.legend()
    
    # 4. Summary Statistics Table
    ax4 = plt.subplot(2, 3, 4)
    ax4.axis('off')
    
    stats_text = f"""
    UAE Agriculture Monitoring Summary
    ──────────────────────────────────
    Total Scenes Processed: {analysis['total_scenes']}
    Date Range: {analysis['date_range']['start']} to {analysis['date_range']['end']}
    
    NDVI Statistics:
    • Mean: {analysis['ndvi_stats']['mean']:.3f}
    • Range: {analysis['ndvi_stats']['min']:.3f} - {analysis['ndvi_stats']['max']:.3f}
    • Std Dev: {analysis['ndvi_stats']['std']:.3f}
    
    Trend: {analysis.get('trend', {}).get('direction', 'Insufficient data')}
    """
    
    if 'comparison' in analysis:
        stats_text += f"\nRecent vs Historical:\n• Change: {analysis['comparison']['change']:+.3f}"
    
    plt.text(0.1, 0.5, stats_text, transform=ax4.transAxes, fontsize=10,
             verticalalignment='center', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
    
    # 5. Seasonal Pattern (if enough data)
    ax5 = plt.subplot(2, 3, 5)
    if len(time_series_df) >= 4:
        time_series_df['month'] = time_series_df['date'].dt.month
        monthly_avg = time_series_df.groupby('month')['ndvi_mean'].mean()
        
        plt.plot(monthly_avg.index, monthly_avg.values, 'o-', linewidth=2, markersize=8)
        plt.title('Seasonal NDVI Pattern', fontsize=12, fontweight='bold')
        plt.xlabel('Month')
        plt.ylabel('Average NDVI')
        plt.xticks(range(1, 13), ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
        plt.grid(True, alpha=0.3)
    else:
        plt.text(0.5, 0.5, 'Insufficient data\nfor seasonal analysis\n(need 4+ scenes)', 
                ha='center', va='center', transform=ax5.transAxes, fontsize=12)
        ax5.set_title('Seasonal Analysis', fontsize=12, fontweight='bold')
    
    # 6. Data Quality Indicators
    ax6 = plt.subplot(2, 3, 6)
    ax6.axis('off')
    
    quality_text = f"""
    Data Quality & Processing Info
    ──────────────────────────────
    Processing Method: AWS Lambda
    Storage: S3 (Lightweight Results)
    AOI: Small Abu Dhabi Area (~1km²)
    
    Data Sources:
    • Sentinel-2 L2A (10m resolution)
    • Cloud cover: <20%
    • Bands: NIR, Red, Green, Blue
    
    Indices Calculated:
    • NDVI (Vegetation Health)
    • Processing: Automated
    • Storage per scene: ~10KB
    """
    
    plt.text(0.1, 0.5, quality_text, transform=ax6.transAxes, fontsize=9,
             verticalalignment='center', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
    
    plt.tight_layout()
    
    # Save visualization
    output_file = output_dir / 'aws_agriculture_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()  # Close figure to free memory in CI/CD
    
    print(f"✓ Visualization saved to {output_file}")

def generate_analysis_report(analysis, time_series_df, output_dir):
    """Generate a comprehensive analysis report"""
    
    print("📋 Generating analysis report...")
    
    report_content = f"""
# UAE Agriculture Monitoring Analysis Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary
This report analyzes vegetation health in a small agricultural area of Abu Dhabi using Sentinel-2 satellite imagery processed through AWS Lambda functions.

## Data Overview
- **Total Scenes Analyzed**: {analysis['total_scenes']}
- **Date Range**: {analysis['date_range']['start']} to {analysis['date_range']['end']}
- **Processing Method**: AWS Lambda (Cloud-Native)
- **Storage Efficiency**: ~10KB per scene (99.5% reduction from raw data)

## Vegetation Health Analysis

### NDVI Statistics
- **Mean NDVI**: {analysis['ndvi_stats']['mean']:.3f}
- **Range**: {analysis['ndvi_stats']['min']:.3f} to {analysis['ndvi_stats']['max']:.3f}
- **Standard Deviation**: {analysis['ndvi_stats']['std']:.3f}

### Interpretation
"""

    # Add interpretation based on NDVI values
    mean_ndvi = analysis['ndvi_stats']['mean']
    if mean_ndvi > 0.3:
        report_content += "- **Good vegetation health** detected in the study area\n"
    elif mean_ndvi > 0.2:
        report_content += "- **Moderate vegetation** present, typical for arid agriculture\n"
    else:
        report_content += "- **Sparse vegetation** detected, characteristic of desert environment\n"

    # Add trend analysis if available
    if 'trend' in analysis:
        trend_dir = analysis['trend']['direction']
        report_content += f"- **Trend Direction**: {trend_dir.capitalize()}\n"
        
        if trend_dir == 'improving':
            report_content += "- Vegetation health is showing positive development\n"
        elif trend_dir == 'declining':
            report_content += "- Vegetation health shows concerning decline\n"
        else:
            report_content += "- Vegetation health remains stable over time\n"

    # Add health distribution
    if 'health_distribution' in analysis:
        report_content += f"\n### Health Classification Distribution\n"
        for health, count in analysis['health_distribution'].items():
            percentage = (count / analysis['total_scenes']) * 100
            report_content += f"- **{health}**: {count} scenes ({percentage:.1f}%)\n"

    report_content += f"""

## Technical Implementation

### AWS Architecture Benefits
- **Cost Efficient**: Processing within free tier limits
- **Scalable**: Automated Lambda-based processing
- **Storage Optimized**: 5GB limit maintained through lightweight outputs
- **Real-time Capable**: On-demand scene processing

### Data Processing Pipeline
1. **Scene Discovery**: STAC API search for low-cloud scenes
2. **Lambda Processing**: Download → Clip → Calculate NDVI → Store results
3. **Automatic Cleanup**: Raw data deleted after processing
4. **Time Series Logging**: Rolling window of results maintained

## Conclusion
The AWS-based agriculture monitoring system successfully demonstrates cloud-native geospatial processing capabilities while maintaining cost efficiency. The automated pipeline provides valuable insights into vegetation health trends in Abu Dhabi's arid agricultural environment.
"""

    # Save report
    report_file = output_dir / 'agriculture_analysis_report.md'
    with open(report_file, 'w') as f:
        f.write(report_content)
    
    print(f"✓ Analysis report saved to {report_file}")

def main(process_new_scene=False):
    """Main analysis workflow - non-interactive for CI/CD"""
    
    print("🚀 === Step 2: AWS Agriculture Data Analysis ===\n")
    
    # Setup
    LOCAL_CACHE_DIR.mkdir(exist_ok=True)
    s3_client, lambda_client = setup_aws_clients()
    
    if not s3_client:
        print("❌ Cannot proceed without AWS access")
        return
    
    # Option to process new scene (controlled by parameter)
    if process_new_scene and lambda_client:
        print("\n📡 Processing new scene...")
        scene_params = {
            'start_date': '2024-07-01',
            'end_date': '2024-08-30'
        }
        
        processing_result = trigger_scene_processing(lambda_client, scene_params)
        if processing_result:
            print(f"✓ New scene processed: {processing_result.get('result', {}).get('scene_id', 'Unknown')}")
    
    # Load and analyze existing results
    print("\n📊 Loading existing analysis results...")
    time_series_df = load_time_series_data(s3_client)
    
    if time_series_df.empty:
        print("❌ No data available for analysis. Please run scene processing first.")
        return
    
    # Perform analysis
    analysis = analyze_vegetation_trends(time_series_df)
    
    # Create output directory
    output_dir = Path('aws_analysis_outputs')
    output_dir.mkdir(exist_ok=True)
    
    # Generate visualizations
    create_aws_visualizations(time_series_df, analysis, output_dir)
    
    # Generate report
    generate_analysis_report(analysis, time_series_df, output_dir)
    
    # Save analysis results
    analysis_file = output_dir / 'analysis_results.json'
    with open(analysis_file, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"\n✅ === Step 2 Complete ===")
    print(f"📁 Outputs saved to: {output_dir}")
    print(f"📊 Processed {analysis['total_scenes']} scenes")
    print(f"🌱 Mean NDVI: {analysis['ndvi_stats']['mean']:.3f}")
    print(f"📈 Trend: {analysis.get('trend', {}).get('direction', 'Insufficient data')}")
    
    # Print file sizes to show efficiency
    total_size = sum(f.stat().st_size for f in output_dir.glob('*') if f.is_file())
    print(f"💾 Total output size: {total_size / 1024:.1f}KB")

if __name__ == "__main__":
    # Check for command line arguments
    process_new = '--process-new' in sys.argv
    main(process_new_scene=process_new)
