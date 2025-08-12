import os
import shutil
from pathlib import Path

def migrate_project_structure():
    """Migrate existing project to CI/CD structure"""
    
    print("🚀 Migrating project to CI/CD structure...")
    
    # Create new directories
    directories = [
        'lambda', 'analysis', 'tests', 'infrastructure', 
        'scripts', '.github/workflows'
    ]
    
    for dir_name in directories:
        Path(dir_name).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created {dir_name}/")
    
    # File migrations
    migrations = [
        # Lambda function
        ('01_aws_satellite_processor.py', 'lambda_function/lambda_function.py'),
        ('aoi.geojson', 'lambda_function/aoi.geojson'),
        
        # Analysis scripts
        ('02_aws_analysis.py', 'analysis/aws_analysis.py'),
        ('03_aws_automation.py', 'analysis/aws_automation.py'),
        ('03_climate_integration.py', 'analysis/climate_integration.py'),
        
        # Infrastructure
        ('trust-policy.json', 'infrastructure/lambda-role-policy.json'),
    ]
    
    for source, destination in migrations:
        if os.path.exists(source):
            shutil.move(source, destination)
            print(f"  📁 Moved {source} → {destination}")
        else:
            print(f"  ⚠️  {source} not found, skipping...")
    
    # Remove old files
    old_files = [
        'deployment_script.py',
        'satellite-processor.zip',
        '03_pipeline.ipynb'  # Since it was interrupted
    ]
    
    for file in old_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"  🗑️  Removed {file}")
    
    print("✅ Migration completed!")
    print("\nNext steps:")
    print("1. git add .")
    print("2. git commit -m 'Migrate to automated CI/CD deployment'")
    print("3. git push origin main")
    print("4. Watch GitHub Actions deploy automatically!")

if __name__ == "__main__":
    migrate_project_structure()
