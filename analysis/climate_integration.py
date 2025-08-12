import boto3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Set headless backend for CI/CD
import matplotlib.pyplot as plt
import json
import os
import sys

class UAEClimateAnalyzer:
    """Enhanced climate data analysis for agriculture - CI/CD Compatible"""
    
    def __init__(self, s3_bucket=None):
        self.bucket = s3_bucket or os.environ.get('S3_BUCKET', 'uae-agri-monitoring')
        
        try:
            self.s3_client = boto3.client('s3')
            print(f"🌡️  Climate Analyzer initialized for bucket: {self.bucket}")
        except Exception as e:
            print(f"❌ Failed to initialize S3 client: {e}")
            sys.exit(1)
    
    def analyze_vegetation_climate_correlation(self):
        """Analyze correlation between vegetation health and climate variables"""
        
        print("🌡️ Analyzing vegetation-climate correlations...")
        
        try:
            # Load vegetation time series
            try:
                veg_response = self.s3_client.get_object(
                    Bucket=self.bucket,
                    Key='time_series/vegetation_log.json'
                )
                veg_data = json.loads(veg_response['Body'].read())
                veg_df = pd.DataFrame(veg_data['scenes'])
                veg_df['date'] = pd.to_datetime(veg_df['date'])
            except Exception as e:
                print(f"❌ Failed to load vegetation data: {e}")
                return None
            
            # Load climate data (assuming it exists from Step 3)
            try:
                climate_files = self.s3_client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix='climate_data/'
                )
                
                if 'Contents' not in climate_files:
                    print("❌ No climate data found. Run climate integration first.")
                    return None
                
                # Load most recent climate file
                latest_climate = max(climate_files['Contents'], key=lambda x: x['LastModified'])
                climate_response = self.s3_client.get_object(
                    Bucket=self.bucket,
                    Key=latest_climate['Key']
                )
                climate_df = pd.read_csv(climate_response['Body'])
                climate_df['date'] = pd.to_datetime(climate_df['date'])
            except Exception as e:
                print(f"❌ Failed to load climate data: {e}")
                return None
            
            # Merge datasets
            merged_df = pd.merge(veg_df, climate_df, on='date', how='inner')
            
            if len(merged_df) == 0:
                print("❌ No overlapping dates between vegetation and climate data")
                return None
            
            # Calculate correlations
            correlations = {}
            climate_vars = ['temperature_avg', 'precipitation', 'humidity', 'heat_stress_index']
            
            for var in climate_vars:
                if var in merged_df.columns:
                    corr = merged_df['ndvi_mean'].corr(merged_df[var])
                    correlations[var] = float(corr)
            
            # Generate insights
            insights = {
                'correlations': correlations,
                'data_points': len(merged_df),
                'date_range': {
                    'start': merged_df['date'].min().strftime('%Y-%m-%d'),
                    'end': merged_df['date'].max().strftime('%Y-%m-%d')
                }
            }
            
            # Identify key relationships
            strong_correlations = {k: v for k, v in correlations.items() if abs(v) > 0.5}
            insights['strong_relationships'] = strong_correlations
            
            # Water stress analysis
            if 'heat_stress_index' in merged_df.columns and 'precipitation' in merged_df.columns:
                stress_periods = merged_df[
                    (merged_df['heat_stress_index'] > 2) & 
                    (merged_df['precipitation'] < 0.1)
                ]
                insights['water_stress_periods'] = len(stress_periods)
                
                if len(stress_periods) > 0:
                    avg_ndvi_stress = stress_periods['ndvi_mean'].mean()
                    avg_ndvi_normal = merged_df[~merged_df.index.isin(stress_periods.index)]['ndvi_mean'].mean()
                    insights['stress_impact'] = {
                        'ndvi_during_stress': float(avg_ndvi_stress),
                        'ndvi_normal': float(avg_ndvi_normal),
                        'impact_magnitude': float(avg_ndvi_normal - avg_ndvi_stress)
                    }
            
            # Save analysis
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=f"analytics/vegetation_climate_correlation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    Body=json.dumps(insights, indent=2),
                    ContentType='application/json'
                )
            except Exception as e:
                print(f"⚠️  Failed to upload correlation analysis to S3: {e}")
            
            print(f"✅ Correlation analysis complete:")
            print(f"   📊 Data points: {insights['data_points']}")
            print(f"   🔗 Strong correlations: {len(strong_correlations)}")
            
            for var, corr in strong_correlations.items():
                direction = "positive" if corr > 0 else "negative"
                print(f"      {var}: {corr:.3f} ({direction})")
            
            return insights
            
        except Exception as e:
            print(f"❌ Correlation analysis failed: {e}")
            return None
    
    def create_climate_visualization(self, output_path='climate_analysis.png'):
        """Create climate analysis visualization - CI/CD compatible"""
        
        print("📈 Creating climate visualization...")
        
        try:
            # Load correlation results
            correlation_results = self.analyze_vegetation_climate_correlation()
            
            if not correlation_results:
                print("❌ No correlation data available for visualization")
                return False
            
            # Set non-interactive backend
            plt.ioff()
            
            # Create visualization
            fig, axes = plt.subplots(2, 2, figsize=(12, 10))
            axes = axes.flatten()
            
            # 1. Correlation heatmap
            correlations = correlation_results['correlations']
            if correlations:
                vars = list(correlations.keys())
                values = list(correlations.values())
                
                ax = axes[0]
                bars = ax.bar(vars, values, color=['red' if v < 0 else 'green' for v in values])
                ax.set_title('Vegetation-Climate Correlations', fontweight='bold')
                ax.set_ylabel('Correlation Coefficient')
                ax.tick_params(axis='x', rotation=45)
                ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
                
                # Add value labels on bars
                for bar, value in zip(bars, values):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + 0.01 * np.sign(height),
                           f'{value:.3f}', ha='center', va='bottom' if height > 0 else 'top')
            
            # 2. Strong correlations summary
            ax = axes[1]
            ax.axis('off')
            
            strong_corrs = correlation_results.get('strong_relationships', {})
            summary_text = f"Climate Analysis Summary\n" + "="*25 + "\n"
            summary_text += f"Data Points: {correlation_results['data_points']}\n"
            summary_text += f"Date Range: {correlation_results['date_range']['start']} to {correlation_results['date_range']['end']}\n\n"
            
            if strong_corrs:
                summary_text += "Strong Correlations (|r| > 0.5):\n"
                for var, corr in strong_corrs.items():
                    direction = "↗" if corr > 0 else "↘"
                    summary_text += f"  {direction} {var}: {corr:.3f}\n"
            else:
                summary_text += "No strong correlations found\n"
            
            if 'stress_impact' in correlation_results:
                impact = correlation_results['stress_impact']
                summary_text += f"\nWater Stress Impact:\n"
                summary_text += f"  NDVI during stress: {impact['ndvi_during_stress']:.3f}\n"
                summary_text += f"  NDVI normal: {impact['ndvi_normal']:.3f}\n"
                summary_text += f"  Impact magnitude: {impact['impact_magnitude']:.3f}\n"
            
            ax.text(0.1, 0.9, summary_text, transform=ax.transAxes, fontsize=10,
                   verticalalignment='top', fontfamily='monospace',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
            
            # 3. Placeholder for future analysis
            ax = axes[2]
            ax.text(0.5, 0.5, 'Future Analysis:\n\n• Seasonal patterns\n• Drought prediction\n• Irrigation optimization', 
                   ha='center', va='center', transform=ax.transAxes, fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
            ax.set_title('Planned Enhancements', fontweight='bold')
            ax.axis('off')
            
            # 4. Data quality indicators
            ax = axes[3]
            ax.axis('off')
            
            quality_text = f"Data Quality Report\n" + "="*20 + "\n"
            quality_text += f"✅ Vegetation data: Available\n"
            quality_text += f"✅ Climate data: Available\n"
            quality_text += f"✅ Data overlap: {correlation_results['data_points']} days\n"
            quality_text += f"✅ Strong correlations: {len(strong_corrs)}\n"
            quality_text += f"\nProcessing: Automated\n"
            quality_text += f"Storage: S3 optimized\n"
            quality_text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            ax.text(0.1, 0.9, quality_text, transform=ax.transAxes, fontsize=10,
                   verticalalignment='top', fontfamily='monospace',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgreen", alpha=0.8))
            
            plt.tight_layout()
            plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close()  # Important for CI/CD
            
            print(f"✅ Climate visualization saved to {output_path}")
            
            # Upload to S3
            try:
                with open(output_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket,
                        Key=f"visualizations/climate_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                        Body=f.read(),
                        ContentType='image/png'
                    )
                print("✅ Climate visualization uploaded to S3")
            except Exception as e:
                print(f"⚠️  Failed to upload visualization to S3: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Climate visualization failed: {e}")
            return False

def create_prediction_model():
    """Simple predictive model for vegetation health - CI/CD compatible"""
    
    print("🤖 Creating vegetation prediction model...")
    
    # This would integrate with your existing data to create
    # a simple predictive model for vegetation health based on
    # climate patterns and historical NDVI data
    
    model_config = {
        'model_type': 'linear_regression',
        'features': ['temperature_avg', 'precipitation', 'humidity'],
        'target': 'ndvi_mean',
        'training_period': '4_months',
        'prediction_horizon': '30_days',
        'created_at': datetime.now().isoformat()
    }
    
    print(f"   📈 Model configuration: {model_config['model_type']}")
    print(f"   🎯 Features: {', '.join(model_config['features'])}")
    print(f"   ⏰ Prediction horizon: {model_config['prediction_horizon']}")
    
    return model_config

def main():
    """Main climate integration workflow - CI/CD compatible"""
    
    print("🌡️ === Climate Integration Analysis ===\n")
    
    try:
        analyzer = UAEClimateAnalyzer()
        
        # Run correlation analysis
        correlation_results = analyzer.analyze_vegetation_climate_correlation()
        
        # Create visualization
        viz_success = analyzer.create_climate_visualization()
        
        # Create prediction model config
        model_config = create_prediction_model()
        
        print(f"\n✅ Climate integration complete:")
        print(f"   📊 Correlation analysis: {'Success' if correlation_results else 'Failed'}")
        print(f"   📈 Visualization: {'Success' if viz_success else 'Failed'}")
        print(f"   🤖 Model config: Success")
        
        return correlation_results is not None
        
    except Exception as e:
        print(f"❌ Climate integration failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
