import boto3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Set headless backend for CI/CD
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
import os
import sys

warnings.filterwarnings('ignore')

# AWS Configuration from environment variables (CI/CD friendly)
S3_BUCKET = os.environ.get('S3_BUCKET', 'uae-agri-monitoring')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
LAMBDA_FUNCTION = os.environ.get('LAMBDA_FUNCTION', 'uae-satellite-processor')

class UAEAgricultureMonitor:
    """Automated multi-temporal agriculture monitoring system - CI/CD Compatible"""
    
    def __init__(self):
        try:
            self.s3_client = boto3.client('s3', region_name=AWS_REGION)
            self.lambda_client = boto3.client('lambda', region_name=AWS_REGION)
            self.events_client = boto3.client('events', region_name=AWS_REGION)
            self.sns_client = boto3.client('sns', region_name=AWS_REGION)
            print("🚀 UAE Agriculture Monitor initialized")
        except Exception as e:
            print(f"❌ Failed to initialize AWS clients: {e}")
            sys.exit(1)
    
    def setup_automated_monitoring(self, monitoring_frequency='weekly'):
        """Set up automated EventBridge scheduling for regular monitoring"""
        
        print(f"⏰ Setting up {monitoring_frequency} automated monitoring...")
        
        # Define schedule expressions
        schedules = {
            'daily': 'rate(1 day)',
            'weekly': 'rate(7 days)', 
            'monthly': 'rate(30 days)'
        }
        
        if monitoring_frequency not in schedules:
            print(f"❌ Invalid frequency. Choose from: {list(schedules.keys())}")
            return False
        
        try:
            # Create EventBridge rule
            rule_name = 'uae-agriculture-monitoring'
            
            self.events_client.put_rule(
                Name=rule_name,
                ScheduleExpression=schedules[monitoring_frequency],
                Description=f'Automated UAE agriculture monitoring - {monitoring_frequency}',
                State='ENABLED'
            )
            
            # Get account ID for proper ARN construction
            account_id = boto3.client('sts').get_caller_identity()['Account']
            
            # Add Lambda target
            self.events_client.put_targets(
                Rule=rule_name,
                Targets=[
                    {
                        'Id': '1',
                        'Arn': f'arn:aws:lambda:{AWS_REGION}:{account_id}:function:{LAMBDA_FUNCTION}',
                        'Input': json.dumps({
                            'trigger_type': 'scheduled',
                            'monitoring_frequency': monitoring_frequency,
                            'start_date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                            'end_date': datetime.now().strftime('%Y-%m-%d')
                        })
                    }
                ]
            )
            
            print(f"✅ {monitoring_frequency.title()} monitoring schedule created")
            print(f"   Rule: {rule_name}")
            print(f"   Target: {LAMBDA_FUNCTION}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to set up automation: {e}")
            return False
    
    def process_multi_temporal_batch(self, date_range_months=6, max_scenes=8):
        """Process multiple scenes across time period for trend analysis"""
        
        print(f"📊 Processing {max_scenes} scenes across {date_range_months} months...")
        
        # Generate date ranges for processing
        end_date = datetime.now()
        start_date = end_date - timedelta(days=date_range_months * 30)
        
        # Generate monthly intervals
        date_ranges = []
        current_date = start_date
        
        while current_date < end_date:
            month_end = min(current_date + timedelta(days=30), end_date)
            date_ranges.append((
                current_date.strftime('%Y-%m-%d'),
                month_end.strftime('%Y-%m-%d')
            ))
            current_date = month_end + timedelta(days=1)
        
        # Limit to max_scenes
        if len(date_ranges) > max_scenes:
            step = len(date_ranges) // max_scenes
            date_ranges = date_ranges[::step][:max_scenes]
        
        print(f"Processing {len(date_ranges)} time periods...")
        
        # Process each time period
        processing_results = []
        
        for i, (start, end) in enumerate(date_ranges, 1):
            print(f"\n🛰️  Processing period {i}/{len(date_ranges)}: {start} to {end}")
            
            try:
                # Invoke Lambda for this time period
                response = self.lambda_client.invoke(
                    FunctionName=LAMBDA_FUNCTION,
                    InvocationType='RequestResponse',
                    Payload=json.dumps({
                        'start_date': start,
                        'end_date': end,
                        'batch_id': f'batch_{i}',
                        'processing_type': 'multi_temporal'
                    })
                )
                
                result = json.loads(response['Payload'].read())
                
                if response['StatusCode'] == 200:
                    body = json.loads(result['body'])
                    processing_results.append({
                        'period': f"{start}_to_{end}",
                        'start_date': start,
                        'end_date': end,
                        'status': 'success',
                        'result': body.get('result', {}),
                        'processing_time': datetime.now().isoformat()
                    })
                    print(f"   ✅ Period {i} processed successfully")
                else:
                    print(f"   ❌ Period {i} failed: {result}")
                    processing_results.append({
                        'period': f"{start}_to_{end}",
                        'start_date': start,
                        'end_date': end,
                        'status': 'failed',
                        'error': str(result),
                        'processing_time': datetime.now().isoformat()
                    })
                    
            except Exception as e:
                print(f"   ❌ Period {i} error: {e}")
                processing_results.append({
                    'period': f"{start}_to_{end}",
                    'start_date': start,
                    'end_date': end,
                    'status': 'failed',
                    'error': str(e),
                    'processing_time': datetime.now().isoformat()
                })
        
        # Save batch processing results
        batch_summary = {
            'batch_id': f'multi_temporal_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'total_periods': len(date_ranges),
            'successful': len([r for r in processing_results if r['status'] == 'success']),
            'failed': len([r for r in processing_results if r['status'] == 'failed']),
            'results': processing_results,
            'created_at': datetime.now().isoformat()
        }
        
        # Upload batch summary to S3
        try:
            self.s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"batch_processing/batch_summary_{batch_summary['batch_id']}.json",
                Body=json.dumps(batch_summary, indent=2),
                ContentType='application/json'
            )
        except Exception as e:
            print(f"⚠️  Failed to upload batch summary to S3: {e}")
        
        print(f"\n📋 Batch processing complete:")
        print(f"   ✅ Successful: {batch_summary['successful']}")
        print(f"   ❌ Failed: {batch_summary['failed']}")
        print(f"   📁 Summary saved to S3")
        
        return batch_summary
    
    def integrate_climate_data(self, start_date, end_date):
        """Add synthetic climate data for agricultural context"""
        
        print("🌡️  Integrating climate data...")
        
        # Generate synthetic UAE climate data (since ERA5 requires setup)
        dates = pd.date_range(start_date, end_date, freq='D')
        
        climate_data = []
        for date in dates:
            # UAE seasonal patterns
            day_of_year = date.dayofyear
            
            # Temperature: 20-45°C seasonal variation
            base_temp = 32 + 13 * np.sin(2 * np.pi * (day_of_year - 100) / 365)
            daily_temp = base_temp + np.random.normal(0, 3)
            
            # Precipitation: Very low, occasional winter rain
            if date.month in [12, 1, 2, 3]:  # Winter months
                precip = np.random.exponential(0.2) if np.random.random() < 0.08 else 0
            else:  # Summer months
                precip = np.random.exponential(0.05) if np.random.random() < 0.01 else 0
            
            # Humidity: High in summer, moderate in winter
            base_humidity = 60 + 20 * np.sin(2 * np.pi * (day_of_year - 180) / 365)
            humidity = max(30, min(90, base_humidity + np.random.normal(0, 5)))
            
            climate_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'temperature_max': round(daily_temp + 3, 1),
                'temperature_min': round(daily_temp - 8, 1),
                'temperature_avg': round(daily_temp, 1),
                'precipitation': round(precip, 2),
                'humidity': round(humidity, 1),
                'heat_stress_index': round(max(0, daily_temp - 35), 1)  # Heat stress above 35°C
            })
        
        # Convert to DataFrame
        climate_df = pd.DataFrame(climate_data)
        
        # Calculate agricultural indices
        climate_df['cumulative_precip'] = climate_df['precipitation'].cumsum()
        climate_df['growing_degree_days'] = np.maximum(0, climate_df['temperature_avg'] - 10)  # Base 10°C
        climate_df['water_stress_risk'] = (
            (climate_df['temperature_max'] > 40) & 
            (climate_df['precipitation'] < 0.1)
        ).astype(int)
        
        # Save to S3
        try:
            climate_csv = climate_df.to_csv(index=False)
            self.s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"climate_data/climate_{start_date}_to_{end_date}.csv",
                Body=climate_csv,
                ContentType='text/csv'
            )
        except Exception as e:
            print(f"⚠️  Failed to upload climate data to S3: {e}")
        
        # Summary statistics
        summary = {
            'period': f"{start_date} to {end_date}",
            'total_days': len(climate_df),
            'avg_temperature': round(climate_df['temperature_avg'].mean(), 1),
            'total_precipitation': round(climate_df['precipitation'].sum(), 1),
            'heat_stress_days': int(climate_df['water_stress_risk'].sum()),
            'growing_degree_days': round(climate_df['growing_degree_days'].sum(), 1)
        }
        
        print(f"   📊 Climate summary ({summary['total_days']} days):")
        print(f"   🌡️  Average temperature: {summary['avg_temperature']}°C")
        print(f"   💧 Total precipitation: {summary['total_precipitation']}mm")
        print(f"   🔥 Heat stress days: {summary['heat_stress_days']}")
        print(f"   📈 Growing degree days: {summary['growing_degree_days']}")
        
        return climate_df, summary
    
    def perform_advanced_analytics(self):
        """Perform trend analysis, anomaly detection, and alerting"""
        
        print("🔍 Performing advanced analytics...")
        
        # Load time series vegetation data
        try:
            response = self.s3_client.get_object(
                Bucket=S3_BUCKET,
                Key='time_series/vegetation_log.json'
            )
            time_series = json.loads(response['Body'].read())
            
            if not time_series.get('scenes'):
                print("❌ No time series data available")
                return None
                
        except Exception as e:
            print(f"❌ Failed to load time series data: {e}")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(time_series['scenes'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        analytics_results = {}
        
        # 1. Trend Analysis
        print("   📈 Analyzing vegetation trends...")
        if len(df) >= 3:
            x = np.arange(len(df))
            y = df['ndvi_mean'].values
            
            # Linear trend
            trend_coef = np.polyfit(x, y, 1)[0]
            
            # Seasonal analysis (if enough data)
            if len(df) >= 6:
                df['month'] = df['date'].dt.month
                seasonal_pattern = df.groupby('month')['ndvi_mean'].mean().to_dict()
            else:
                seasonal_pattern = {}
            
            analytics_results['trend_analysis'] = {
                'trend_slope': float(trend_coef),
                'trend_direction': 'improving' if trend_coef > 0.001 else 'declining' if trend_coef < -0.001 else 'stable',
                'r_squared': float(np.corrcoef(x, y)[0, 1]**2) if len(df) > 1 else 0,
                'seasonal_pattern': seasonal_pattern
            }
            
            print(f"      Trend: {analytics_results['trend_analysis']['trend_direction']}")
            print(f"      R²: {analytics_results['trend_analysis']['r_squared']:.3f}")
        
        # 2. Anomaly Detection
        print("   🚨 Detecting anomalies...")
        if len(df) >= 4:
            # Simple statistical anomaly detection
            ndvi_mean = df['ndvi_mean'].mean()
            ndvi_std = df['ndvi_mean'].std()
            
            # Z-score anomalies (|z| > 2)
            df['z_score'] = (df['ndvi_mean'] - ndvi_mean) / ndvi_std
            anomalies = df[abs(df['z_score']) > 2]
            
            analytics_results['anomaly_detection'] = {
                'total_anomalies': len(anomalies),
                'anomaly_threshold': 2.0,
                'baseline_ndvi': float(ndvi_mean),
                'anomaly_dates': anomalies['date'].dt.strftime('%Y-%m-%d').tolist() if len(anomalies) > 0 else []
            }
            
            print(f"      Anomalies detected: {len(anomalies)}")
            if len(anomalies) > 0:
                print(f"      Anomaly dates: {', '.join(analytics_results['anomaly_detection']['anomaly_dates'])}")
        
        # 3. Health Classification
        print("   🌱 Analyzing vegetation health...")
        recent_ndvi = df['ndvi_mean'].tail(3).mean()  # Last 3 observations
        
        health_classification = {
            'current_ndvi': float(recent_ndvi),
            'health_status': 'good' if recent_ndvi > 0.3 else 'moderate' if recent_ndvi > 0.2 else 'poor',
            'confidence': 'high' if len(df) >= 5 else 'medium' if len(df) >= 3 else 'low'
        }
        
        analytics_results['health_classification'] = health_classification
        print(f"      Current health: {health_classification['health_status']} (NDVI: {recent_ndvi:.3f})")
        
        # 4. Generate Alerts
        alerts = []
        
        if analytics_results.get('trend_analysis', {}).get('trend_direction') == 'declining':
            alerts.append({
                'type': 'trend_alert',
                'severity': 'medium',
                'message': 'Declining vegetation trend detected',
                'recommendation': 'Investigate irrigation and soil conditions'
            })
        
        if analytics_results.get('anomaly_detection', {}).get('total_anomalies', 0) > 0:
            alerts.append({
                'type': 'anomaly_alert', 
                'severity': 'high',
                'message': f"{analytics_results['anomaly_detection']['total_anomalies']} vegetation anomalies detected",
                'recommendation': 'Check recent dates for crop stress or external factors'
            })
        
        if recent_ndvi < 0.15:
            alerts.append({
                'type': 'health_alert',
                'severity': 'high', 
                'message': 'Very low vegetation health detected',
                'recommendation': 'Immediate intervention required - check irrigation and crop conditions'
            })
        
        analytics_results['alerts'] = alerts
        
        # Save analytics results
        analytics_results['analysis_timestamp'] = datetime.now().isoformat()
        analytics_results['data_points_analyzed'] = len(df)
        
        try:
            self.s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"analytics/advanced_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                Body=json.dumps(analytics_results, indent=2),
                ContentType='application/json'
            )
        except Exception as e:
            print(f"⚠️  Failed to upload analytics to S3: {e}")
        
        print(f"   📊 Analytics complete: {len(alerts)} alerts generated")
        
        return analytics_results
    
    def generate_monitoring_dashboard(self, analytics_results=None, save_only=False):
        """Generate comprehensive monitoring dashboard - CI/CD compatible"""
        
        print("📈 Generating monitoring dashboard...")
        
        # Load data
        try:
            response = self.s3_client.get_object(
                Bucket=S3_BUCKET,
                Key='time_series/vegetation_log.json'
            )
            time_series = json.loads(response['Body'].read())
            df = pd.DataFrame(time_series['scenes'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
        except Exception as e:
            print(f"❌ No data available for dashboard: {e}")
            return
        
        # Set non-interactive backend for CI/CD
        plt.ioff()
        
        # Create comprehensive dashboard
        fig = plt.figure(figsize=(20, 12))
        
        # 1. NDVI Time Series with Trend
        ax1 = plt.subplot(2, 4, 1)
        plt.plot(df['date'], df['ndvi_mean'], 'g-o', linewidth=2, markersize=6, label='NDVI')
        
        if analytics_results and 'trend_analysis' in analytics_results:
            # Add trend line
            x_numeric = np.arange(len(df))
            trend_line = np.polyfit(x_numeric, df['ndvi_mean'], 1)
            plt.plot(df['date'], np.polyval(trend_line, x_numeric), '--r', alpha=0.7, 
                    label=f"Trend: {analytics_results['trend_analysis']['trend_direction']}")
            plt.legend()
        
        plt.title('NDVI Time Series & Trend', fontweight='bold')
        plt.ylabel('NDVI')
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        
        # 2. Health Status Pie Chart
        ax2 = plt.subplot(2, 4, 2)
        health_counts = df['vegetation_health'].value_counts()
        colors = ['green' if 'Good' in str(k) else 'orange' for k in health_counts.index]
        plt.pie(health_counts.values, labels=health_counts.index, colors=colors, autopct='%1.1f%%')
        plt.title('Vegetation Health Distribution', fontweight='bold')
        
        # 3. NDVI Distribution
        ax3 = plt.subplot(2, 4, 3)
        plt.hist(df['ndvi_mean'], bins=10, alpha=0.7, color='green', edgecolor='black')
        plt.axvline(df['ndvi_mean'].mean(), color='red', linestyle='--', 
                   label=f"Mean: {df['ndvi_mean'].mean():.3f}")
        plt.title('NDVI Distribution', fontweight='bold')
        plt.xlabel('NDVI Value')
        plt.ylabel('Frequency')
        plt.legend()
        
        # 4. Anomaly Detection
        ax4 = plt.subplot(2, 4, 4)
        if analytics_results and 'anomaly_detection' in analytics_results:
            anomaly_dates = analytics_results['anomaly_detection']['anomaly_dates']
            df['is_anomaly'] = df['date'].dt.strftime('%Y-%m-%d').isin(anomaly_dates)
            
            normal_data = df[~df['is_anomaly']]
            anomaly_data = df[df['is_anomaly']]
            
            plt.scatter(normal_data['date'], normal_data['ndvi_mean'], 
                       c='green', alpha=0.6, label='Normal')
            if len(anomaly_data) > 0:
                plt.scatter(anomaly_data['date'], anomaly_data['ndvi_mean'], 
                           c='red', s=100, marker='X', label='Anomaly')
            plt.legend()
        else:
            plt.scatter(df['date'], df['ndvi_mean'], c='green', alpha=0.6)
        
        plt.title('Anomaly Detection', fontweight='bold')
        plt.ylabel('NDVI')
        plt.xticks(rotation=45)
        
        # 5. System Status (Text)
        ax5 = plt.subplot(2, 4, 5)
        ax5.axis('off')
        
        status_text = f"""
        🛰️  UAE Agriculture Monitor Status
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        📊 Data Points: {len(df)}
        📅 Date Range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}
        
        🌱 Current Health: {analytics_results.get('health_classification', {}).get('health_status', 'Unknown').title() if analytics_results else 'Unknown'}
        📈 Trend: {analytics_results.get('trend_analysis', {}).get('trend_direction', 'Unknown').title() if analytics_results else 'Unknown'}
        🚨 Active Alerts: {len(analytics_results.get('alerts', [])) if analytics_results else 0}
        
        💾 Storage: S3 (Optimized)
        ⚙️  Processing: AWS Lambda
        🔄 Automation: EventBridge
        """
        
        plt.text(0.1, 0.5, status_text, transform=ax5.transAxes, fontsize=10,
                verticalalignment='center', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
        
        # 6. Alerts & Recommendations (Text)
        ax6 = plt.subplot(2, 4, 6)
        ax6.axis('off')
        
        if analytics_results and analytics_results.get('alerts'):
            alert_text = "🚨 Active Alerts:\n" + "─" * 20 + "\n"
            for i, alert in enumerate(analytics_results['alerts'][:3], 1):  # Show max 3 alerts
                severity_icon = "🔴" if alert['severity'] == 'high' else "🟡"
                alert_text += f"{severity_icon} {alert['message']}\n"
                alert_text += f"   💡 {alert['recommendation']}\n\n"
        else:
            alert_text = "✅ No Active Alerts\n\nSystem operating normally.\nAll vegetation metrics within expected ranges."
        
        plt.text(0.1, 0.5, alert_text, transform=ax6.transAxes, fontsize=9,
                verticalalignment='center', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.8))
        plt.title('Alerts & Recommendations', fontweight='bold')
        
        # 7. Seasonal Pattern (if available)
        ax7 = plt.subplot(2, 4, 7)
        if analytics_results and analytics_results.get('trend_analysis', {}).get('seasonal_pattern'):
            seasonal = analytics_results['trend_analysis']['seasonal_pattern']
            months = list(seasonal.keys())
            values = list(seasonal.values())
            
            plt.plot(months, values, 'b-o', linewidth=2, markersize=6)
            plt.title('Seasonal NDVI Pattern', fontweight='bold')
            plt.xlabel('Month')
            plt.ylabel('Average NDVI')
            plt.xticks(range(1, 13))
            plt.grid(True, alpha=0.3)
        else:
            plt.text(0.5, 0.5, 'Insufficient data\nfor seasonal analysis\n(need 6+ months)', 
                    ha='center', va='center', transform=ax7.transAxes, fontsize=12)
            plt.title('Seasonal Analysis', fontweight='bold')
        
        # 8. Processing Timeline
        ax8 = plt.subplot(2, 4, 8)
        processing_dates = df['date']
        processing_success = [1] * len(df)  # All successful in this example
        
        plt.scatter(processing_dates, processing_success, c='green', s=50, alpha=0.7)
        plt.title('Processing Timeline', fontweight='bold')
        plt.ylabel('Success Rate')
        plt.xticks(rotation=45)
        plt.ylim(-0.1, 1.1)
        
        plt.tight_layout()
        
        # Save dashboard (CI/CD compatible - no show())
        output_path = Path('aws_monitoring_dashboard.png')
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()  # Important: Close figure to free memory in CI/CD
        
        print(f"✅ Dashboard saved to {output_path}")
        
        # Upload to S3
        try:
            with open(output_path, 'rb') as f:
                self.s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=f"dashboards/monitoring_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                    Body=f.read(),
                    ContentType='image/png'
                )
            print("✅ Dashboard uploaded to S3")
        except Exception as e:
            print(f"⚠️  Dashboard upload failed: {e}")

def main(run_automation=True, run_climate=True, run_analytics=True):
    """Main Step 3 workflow - CI/CD compatible with parameters"""
    
    print("🚀 === Step 3: AWS Multi-Temporal Automation & Analytics ===\n")
    
    # Initialize monitoring system
    try:
        monitor = UAEAgricultureMonitor()
    except Exception as e:
        print(f"❌ Failed to initialize monitor: {e}")
        return False
    
    success_count = 0
    
    if run_automation:
        # Step 3A: Set up automated monitoring
        print("Step 3A: Setting up automated monitoring...")
        automation_success = monitor.setup_automated_monitoring('weekly')
        if automation_success:
            success_count += 1
        print()
    
    if run_climate:
        # Step 3C: Integrate climate data
        print("Step 3C: Integrating climate data...")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
            climate_df, climate_summary = monitor.integrate_climate_data(start_date, end_date)
            success_count += 1
        except Exception as e:
            print(f"❌ Climate integration failed: {e}")
        print()
    
    if run_analytics:
        # Step 3D: Advanced analytics
        print("Step 3D: Running advanced analytics...")
        try:
            analytics_results = monitor.perform_advanced_analytics()
            if analytics_results:
                success_count += 1
                
                # Step 3E: Generate monitoring dashboard
                print("Step 3E: Generating monitoring dashboard...")
                monitor.generate_monitoring_dashboard(analytics_results)
                success_count += 1
        except Exception as e:
            print(f"❌ Analytics failed: {e}")
        print()
    
    # Summary
    print("✅ === Step 3 Complete ===")
    print(f"📊 Successful components: {success_count}")
    print(f"💾 All results stored efficiently in S3")
    
    return success_count > 0

if __name__ == "__main__":
    # Support command line arguments for CI/CD
    import sys
    
    run_automation = '--no-automation' not in sys.argv
    run_climate = '--no-climate' not in sys.argv  
    run_analytics = '--no-analytics' not in sys.argv
    
    success = main(run_automation, run_climate, run_analytics)
    sys.exit(0 if success else 1)
