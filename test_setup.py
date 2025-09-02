#!/usr/bin/env python3
"""
Test script to verify all components are properly configured
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed, using system environment variables only")

def test_environment_variables():
    """Test if all required environment variables are set"""
    print("\n🔍 Testing Environment Variables...")
    
    required_vars = {
        'SMARTLEAD_API_KEY': 'Smartlead API Key',
        'SLACK_BOT_TOKEN': 'Slack Bot Token',
        'SLACK_CHANNEL_ID': 'Slack Channel ID',
        'DATABASE_URL': 'Database Connection String'
    }
    
    all_set = True
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if value:
            # Mask sensitive values
            if 'TOKEN' in var_name or 'KEY' in var_name:
                masked_value = value[:10] + '...' + value[-4:] if len(value) > 14 else '***'
            else:
                masked_value = value[:20] + '...' if len(value) > 20 else value
            print(f"✅ {description}: {masked_value}")
        else:
            print(f"❌ {description}: NOT SET")
            all_set = False
    
    return all_set

def test_smartlead_api():
    """Test Smartlead API connection"""
    print("\n🔍 Testing Smartlead API...")
    
    try:
        import requests
        api_key = os.getenv('SMARTLEAD_API_KEY')
        if not api_key:
            print("❌ API key not set")
            return False
        
        response = requests.get(
            'https://server.smartlead.ai/api/email-account/get-total-email-accounts',
            params={'api_key': api_key, 'offset': 0, 'limit': 1},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                accounts = data.get('data', {}).get('email_accounts', [])
                print(f"✅ API connection successful")
                print(f"   Found {len(accounts)} account(s) in test query")
                return True
            else:
                print(f"❌ API error: {data.get('message')}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_slack_connection():
    """Test Slack bot connection"""
    print("\n🔍 Testing Slack Connection...")
    
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        token = os.getenv('SLACK_BOT_TOKEN')
        if not token:
            print("❌ Slack bot token not set")
            return False
        
        client = WebClient(token=token)
        
        # Test auth
        response = client.auth_test()
        print(f"✅ Slack authentication successful")
        print(f"   Bot Name: {response['user']}")
        print(f"   Team: {response['team']}")
        
        # Test channel access
        channel_id = os.getenv('SLACK_CHANNEL_ID', '#general')
        try:
            # Try to get channel info
            if channel_id.startswith('#'):
                print(f"   Channel: {channel_id}")
            else:
                response = client.conversations_info(channel=channel_id)
                print(f"   Channel: #{response['channel']['name']}")
            return True
        except SlackApiError as e:
            if e.response['error'] == 'channel_not_found':
                print(f"⚠️  Warning: Channel {channel_id} not found or bot not invited")
                print("   Make sure to invite the bot to the channel")
            return True  # Auth worked, channel access can be fixed
            
    except ImportError:
        print("❌ slack_sdk not installed")
        return False
    except Exception as e:
        print(f"❌ Slack connection error: {e}")
        return False

def test_database_connection():
    """Test database connection"""
    print("\n🔍 Testing Database Connection...")
    
    try:
        import psycopg2
        
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print("❌ Database URL not set")
            return False
        
        conn = psycopg2.connect(db_url, connect_timeout=5)
        cursor = conn.cursor()
        
        # Test connection
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Database connection successful")
        print(f"   PostgreSQL: {version.split(',')[0]}")
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'disconnected_accounts'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("✅ Table 'disconnected_accounts' exists")
            
            # Get row count
            cursor.execute("SELECT COUNT(*) FROM disconnected_accounts;")
            count = cursor.fetchone()[0]
            print(f"   Current records: {count}")
        else:
            print("⚠️  Table 'disconnected_accounts' does not exist (will be created on first run)")
        
        conn.close()
        return True
        
    except ImportError:
        print("❌ psycopg2 not installed")
        return False
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def test_file_structure():
    """Test if required directories exist"""
    print("\n🔍 Testing File Structure...")
    
    directories = {
        'audit_logs': 'Audit logs directory',
        'state': 'State directory'
    }
    
    all_exist = True
    for dir_name, description in directories.items():
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"✅ {description}: {dir_path.absolute()}")
        else:
            print(f"⚠️  {description}: Does not exist (will be created)")
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"   Created: {dir_path.absolute()}")
            except Exception as e:
                print(f"   ❌ Failed to create: {e}")
                all_exist = False
    
    return all_exist

def test_dependencies():
    """Test if all required Python packages are installed"""
    print("\n🔍 Testing Python Dependencies...")
    
    required_packages = {
        'requests': 'HTTP requests library',
        'psycopg2': 'PostgreSQL adapter',
        'slack_sdk': 'Slack SDK',
        'tabulate': 'Table formatting',
        'backoff': 'Retry logic'
    }
    
    all_installed = True
    for package_name, description in required_packages.items():
        try:
            __import__(package_name)
            print(f"✅ {description} ({package_name})")
        except ImportError:
            print(f"❌ {description} ({package_name}) - NOT INSTALLED")
            all_installed = False
    
    return all_installed

def main():
    """Run all tests"""
    print("=" * 60)
    print("Smartlead Monitor Setup Test")
    print("=" * 60)
    
    # Check Python version
    print(f"\n🐍 Python Version: {sys.version}")
    if sys.version_info < (3, 8):
        print("⚠️  Warning: Python 3.8+ recommended")
    
    # Run tests
    results = {
        'Dependencies': test_dependencies(),
        'Environment': test_environment_variables(),
        'File Structure': test_file_structure(),
        'Smartlead API': test_smartlead_api(),
        'Slack': test_slack_connection(),
        'Database': test_database_connection()
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Run the monitor for the first time:")
        print("   python smartlead_monitor.py --first-run")
        print("2. Set up scheduled execution (hourly)")
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("1. Install missing packages: pip install -r requirements.txt")
        print("2. Set environment variables in .env file")
        print("3. Verify API keys and tokens are correct")
        print("4. Ensure Slack bot is invited to the channel")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
