#!/usr/bin/env python3
"""
Smartlead Account Disconnection Monitor
Monitors Smartlead accounts for disconnections and sends notifications to Slack
"""

import os
import sys
import json
import time
import csv
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
import requests
from dataclasses import dataclass, asdict
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import hashlib
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tabulate import tabulate
import backoff

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smartlead_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    # API Configuration - Using Bearer Token instead of API Key
    SMARTLEAD_BEARER_TOKEN = os.getenv('SMARTLEAD_BEARER_TOKEN')
    SMARTLEAD_BASE_URL = 'https://server.smartlead.ai/api'
    
    # Slack Configuration
    SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
    SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID', '#monitoring')
    
    # Database Configuration - Use transaction pooler for serverless environments
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:SB0dailyreporting@db.auzoezucrrhrtmaucbbg.supabase.co:6543/postgres?pgbouncer=true')
    
    # File paths
    CSV_DIR = Path(os.getenv('CSV_DIR', './audit_logs'))
    STATE_FILE = Path(os.getenv('STATE_FILE', './state/last_check.json'))
    
    # Rate limiting
    REQUESTS_PER_2_SECONDS = 10
    MAX_RETRIES = 3
    
    # Data retention
    RETENTION_DAYS = 30

@dataclass
class EmailAccount:
    """Data class for email account information"""
    id: int
    from_name: str
    from_email: str
    type: str
    is_smtp_success: bool
    is_imap_success: bool
    tags: List[str]
    message_per_day: int
    daily_sent_count: int
    client_id: Optional[str] = None
    
    @property
    def is_disconnected(self) -> bool:
        return not (self.is_smtp_success and self.is_imap_success)
    
    @property
    def disconnection_type(self) -> str:
        if not self.is_smtp_success and not self.is_imap_success:
            return "BOTH"
        elif not self.is_smtp_success:
            return "SMTP"
        elif not self.is_imap_success:
            return "IMAP"
        return "CONNECTED"

class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
    
    def wait_if_needed(self):
        now = time.time()
        # Remove old calls outside the period
        self.calls = [call_time for call_time in self.calls if now - call_time < self.period]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0]) + 0.1
            if sleep_time > 0:
                logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        self.calls.append(time.time())

class SmartleadAPI:
    """Smartlead API client with rate limiting and retry logic"""
    
    def __init__(self, bearer_token: str, base_url: str):
        self.bearer_token = bearer_token
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Authorization': f'Bearer {bearer_token}',
            'Content-Type': 'application/json'
        })
        self.rate_limiter = RateLimiter(Config.REQUESTS_PER_2_SECONDS, 2.0)
    
    @backoff.on_exception(
        backoff.expo,
        (requests.RequestException, requests.Timeout),
        max_tries=Config.MAX_RETRIES,
        max_time=60
    )
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Make API request with retry logic"""
        self.rate_limiter.wait_if_needed()
        
        # Don't add api_key to params for Bearer auth
        url = f"{self.base_url}/{endpoint}"
        
        logger.debug(f"Making request to {url}")
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    def fetch_disconnected_accounts(self) -> List[EmailAccount]:
        """Fetch only disconnected accounts using the dedicated endpoint"""
        logger.info("Fetching disconnected accounts directly...")
        
        disconnected = []
        offset = 0
        limit = 10000  # Larger limit for faster fetching
        
        try:
            response = self._make_request(
                'email-account/get-total-email-accounts',
                {
                    'offset': offset, 
                    'limit': limit,
                    'isImapSuccess': 'false',
                    'isSmtpSuccess': 'false'
                }
            )
            
            if not response.get('ok'):
                logger.error(f"API error: {response.get('message')}")
                return disconnected
            
            email_accounts = response.get('data', {}).get('email_accounts', [])
            logger.info(f"Found {len(email_accounts)} disconnected accounts")
            
            for acc in email_accounts:
                tags = []
                for tag_mapping in acc.get('email_account_tag_mappings', []):
                    if 'tag' in tag_mapping and 'name' in tag_mapping['tag']:
                        tags.append(tag_mapping['tag']['name'])
                
                account = EmailAccount(
                    id=acc['id'],
                    from_name=acc.get('from_name', ''),
                    from_email=acc.get('from_email', ''),
                    type=acc.get('type', 'UNKNOWN'),
                    is_smtp_success=acc.get('is_smtp_success', False),
                    is_imap_success=acc.get('is_imap_success', False),
                    tags=tags,
                    message_per_day=acc.get('message_per_day', 0),
                    daily_sent_count=acc.get('daily_sent_count', 0),
                    client_id=acc.get('client_id')
                )
                disconnected.append(account)
                
        except Exception as e:
            logger.error(f"Error fetching disconnected accounts: {e}")
            raise
        
        return disconnected
    
    def fetch_connected_account_ids(self) -> Set[int]:
        """Fetch only IDs of connected accounts for reconnection tracking"""
        logger.info("Fetching connected account IDs...")
        
        connected_ids = set()
        offset = 0
        limit = 10000  # Larger limit
        
        while True:
            try:
                # This fetches ALL accounts - we'll extract connected ones
                response = self._make_request(
                    'email-account/get-total-email-accounts',
                    {'offset': offset, 'limit': limit}
                )
                
                if not response.get('ok'):
                    break
                
                email_accounts = response.get('data', {}).get('email_accounts', [])
                
                if not email_accounts:
                    break
                
                # Only store IDs of connected accounts
                for acc in email_accounts:
                    is_smtp = acc.get('is_smtp_success', False)
                    is_imap = acc.get('is_imap_success', False)
                    if is_smtp and is_imap:
                        connected_ids.add(acc['id'])
                
                logger.info(f"Processed {offset + len(email_accounts)} accounts, found {len(connected_ids)} connected...")
                
                if len(email_accounts) < limit:
                    break
                    
                offset += limit
                
            except Exception as e:
                logger.error(f"Error at offset {offset}: {e}")
                if offset == 0:
                    raise
                break
        
        logger.info(f"Total connected accounts: {len(connected_ids)}")
        return connected_ids

class DatabaseManager:
    """Manager for Supabase database operations"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        # Only create table if needed, don't fail if network issues
        try:
            self._ensure_table_exists()
        except Exception as e:
            logger.warning(f"Could not verify/create table (may already exist): {e}")
    
    def _get_connection(self):
        """Get database connection with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Try connection with shorter timeout
                conn = psycopg2.connect(self.connection_string, connect_timeout=10)
                return conn
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
    
    def _ensure_table_exists(self):
        """Create table if it doesn't exist"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS disconnected_accounts (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            from_name VARCHAR(255),
            from_email VARCHAR(255) NOT NULL,
            account_type VARCHAR(50),
            disconnection_type VARCHAR(20),
            tags TEXT,
            detected_at TIMESTAMP NOT NULL,
            resolved_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            check_run_id VARCHAR(50),
            UNIQUE(account_id, detected_at)
        );
        
        CREATE INDEX IF NOT EXISTS idx_account_id ON disconnected_accounts(account_id);
        CREATE INDEX IF NOT EXISTS idx_detected_at ON disconnected_accounts(detected_at);
        CREATE INDEX IF NOT EXISTS idx_is_active ON disconnected_accounts(is_active);
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_table_sql)
                conn.commit()
            logger.info("Database table ensured")
        except Exception as e:
            logger.error(f"Error creating table: {e}")
    
    def get_active_disconnections(self) -> Set[int]:
        """Get currently active disconnected account IDs"""
        query = """
        SELECT DISTINCT account_id 
        FROM disconnected_accounts 
        WHERE is_active = TRUE
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error fetching active disconnections: {e}")
            return set()
    
    def record_disconnections(self, accounts: List[EmailAccount], check_run_id: str) -> List[EmailAccount]:
        """Record new disconnections and return newly disconnected accounts"""
        if not accounts:
            return []
            
        active_disconnections = self.get_active_disconnections()
        newly_disconnected = []
        
        insert_query = """
        INSERT INTO disconnected_accounts 
        (account_id, from_name, from_email, account_type, disconnection_type, tags, detected_at, check_run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (account_id, detected_at) DO NOTHING
        """
        
        update_active_query = """
        UPDATE disconnected_accounts 
        SET is_active = TRUE 
        WHERE account_id = %s AND is_active = FALSE
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Prepare batch data
                    insert_data = []
                    reactivate_ids = []
                    
                    for account in accounts:
                        if account.is_disconnected:
                            tags_str = ','.join(account.tags) if account.tags else ''
                            
                            # Check if this is a new disconnection
                            if account.id not in active_disconnections:
                                newly_disconnected.append(account)
                                
                                # Add to batch insert
                                insert_data.append((
                                    account.id,
                                    account.from_name,
                                    account.from_email,
                                    account.type,
                                    account.disconnection_type,
                                    tags_str,
                                    datetime.now(),
                                    check_run_id
                                ))
                                
                                # Track for reactivation
                                reactivate_ids.append(account.id)
                    
                    # Bulk insert new disconnections
                    if insert_data:
                        from psycopg2.extras import execute_batch
                        execute_batch(cursor, insert_query, insert_data, page_size=100)
                        logger.info(f"Bulk inserted {len(insert_data)} new disconnection records")
                    
                    # Bulk update reactivations
                    if reactivate_ids:
                        execute_batch(cursor, update_active_query, [(id,) for id in reactivate_ids], page_size=100)
                        logger.info(f"Reactivated {len(reactivate_ids)} previously resolved accounts")
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error recording disconnections: {e}")
        
        return newly_disconnected
    
    def resolve_reconnections(self, connected_account_ids: Set[int]):
        """Mark accounts as resolved if they've reconnected"""
        update_query = """
        UPDATE disconnected_accounts 
        SET is_active = FALSE, resolved_at = %s 
        WHERE account_id = %s AND is_active = TRUE
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    for account_id in connected_account_ids:
                        cursor.execute(update_query, (datetime.now(), account_id))
                conn.commit()
                
                if connected_account_ids:
                    logger.info(f"Resolved {len(connected_account_ids)} reconnected accounts")
        except Exception as e:
            logger.error(f"Error resolving reconnections: {e}")
    
    def cleanup_old_records(self, retention_days: int = 30):
        """Clean up old records beyond retention period"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        delete_query = """
        DELETE FROM disconnected_accounts 
        WHERE detected_at < %s AND is_active = FALSE
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_query, (cutoff_date,))
                    deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old records")
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")

class CSVLogger:
    """Logger for CSV audit trail"""
    
    def __init__(self, csv_dir: Path):
        self.csv_dir = csv_dir
        self.csv_dir.mkdir(parents=True, exist_ok=True)
    
    def log_disconnections(self, accounts: List[EmailAccount], check_run_id: str):
        """Log disconnections to CSV file"""
        if not accounts:
            return
        
        timestamp = datetime.now()
        filename = self.csv_dir / f"disconnections_{timestamp.strftime('%Y%m')}.csv"
        
        file_exists = filename.exists()
        
        try:
            with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'timestamp', 'check_run_id', 'account_id', 'from_name', 
                    'from_email', 'account_type', 'disconnection_type', 
                    'tags', 'message_per_day', 'daily_sent_count'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                for account in accounts:
                    writer.writerow({
                        'timestamp': timestamp.isoformat(),
                        'check_run_id': check_run_id,
                        'account_id': account.id,
                        'from_name': account.from_name,
                        'from_email': account.from_email,
                        'account_type': account.type,
                        'disconnection_type': account.disconnection_type,
                        'tags': ','.join(account.tags) if account.tags else '',
                        'message_per_day': account.message_per_day,
                        'daily_sent_count': account.daily_sent_count
                    })
            
            logger.info(f"Logged {len(accounts)} disconnections to CSV")
        except Exception as e:
            logger.error(f"Error writing to CSV: {e}")

class SlackNotifier:
    """Slack notification handler"""
    
    def __init__(self, bot_token: str, channel_id: str):
        self.client = WebClient(token=bot_token)
        self.channel_id = channel_id
    
    def send_disconnection_alert(self, accounts: List[EmailAccount], check_run_id: str):
        """Send disconnection alert to Slack"""
        if not accounts:
            logger.info("No new disconnections to report")
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Create summary
        summary = f"🔴 *{len(accounts)} New Account Disconnection(s) Detected*\n"
        summary += f"_Check Time: {timestamp}_\n"
        summary += f"_Run ID: {check_run_id}_\n\n"
        
        # Group by disconnection type
        smtp_only = [a for a in accounts if a.disconnection_type == "SMTP"]
        imap_only = [a for a in accounts if a.disconnection_type == "IMAP"]
        both = [a for a in accounts if a.disconnection_type == "BOTH"]
        
        if both:
            summary += f"• Both SMTP & IMAP: {len(both)} accounts\n"
        if smtp_only:
            summary += f"• SMTP Only: {len(smtp_only)} accounts\n"
        if imap_only:
            summary += f"• IMAP Only: {len(imap_only)} accounts\n"
        
        # Create detailed table
        table_data = []
        for acc in accounts[:50]:  # Limit to 50 for Slack message size
            table_data.append([
                acc.id,
                acc.from_email[:30],  # Truncate long emails
                acc.from_name[:20],  # Truncate long names
                acc.type,
                acc.disconnection_type,
                ', '.join(acc.tags[:3]) if acc.tags else 'None'  # First 3 tags
            ])
        
        headers = ['ID', 'Email', 'Name', 'Type', 'Disconnection', 'Tags']
        table = tabulate(table_data, headers=headers, tablefmt='simple')
        
        # Construct message
        message = summary + "\n```\n" + table + "\n```"
        
        if len(accounts) > 50:
            message += f"\n_... and {len(accounts) - 50} more accounts_"
        
        # Add action suggestions
        message += "\n\n*Recommended Actions:*\n"
        message += "1. Check affected email accounts in Smartlead dashboard\n"
        message += "2. Verify email provider connectivity\n"
        message += "3. Re-authenticate affected accounts if needed\n"
        
        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                text=message,
                mrkdwn=True
            )
            logger.info(f"Slack notification sent successfully")
        except SlackApiError as e:
            logger.error(f"Error sending Slack message: {e.response['error']}")
    
    def send_error_notification(self, error_message: str, check_run_id: str):
        """Send error notification to Slack"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        message = f"⚠️ *Smartlead Monitor Error*\n"
        message += f"_Time: {timestamp}_\n"
        message += f"_Run ID: {check_run_id}_\n\n"
        message += f"```{error_message}```\n"
        message += "The monitor will retry on the next scheduled run."
        
        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                text=message,
                mrkdwn=True
            )
        except SlackApiError as e:
            logger.error(f"Error sending error notification: {e.response['error']}")

class StateManager:
    """Manage application state"""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_state(self, state: Dict):
        """Save current state"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def load_state(self) -> Dict:
        """Load previous state"""
        if not self.state_file.exists():
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}

class SmartleadMonitor:
    """Main monitor orchestrator"""
    
    def __init__(self):
        self.api = SmartleadAPI(Config.SMARTLEAD_BEARER_TOKEN, Config.SMARTLEAD_BASE_URL)
        self.db = DatabaseManager(Config.DATABASE_URL)
        self.csv_logger = CSVLogger(Config.CSV_DIR)
        self.slack = SlackNotifier(Config.SLACK_BOT_TOKEN, Config.SLACK_CHANNEL_ID)
        self.state_manager = StateManager(Config.STATE_FILE)
    
    def generate_run_id(self) -> str:
        """Generate unique run ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
        return f"{timestamp}_{random_hash}"
    
    def run_check(self, is_first_run: bool = False):
        """Run the monitoring check"""
        check_run_id = self.generate_run_id()
        logger.info(f"Starting check run: {check_run_id}")
        
        # Add timeout protection
        start_time = time.time()
        max_runtime = 600  # 10 minutes max
        
        try:
            # Load previous state
            state = self.state_manager.load_state()
            last_check = state.get('last_check')
            
            # Determine if this is the first run
            if not last_check:
                is_first_run = True
            
            # OPTIMIZED: Fetch disconnected accounts directly
            logger.info("Step 1: Fetching disconnected accounts...")
            disconnected = self.api.fetch_disconnected_accounts()
            
            # Check timeout
            if time.time() - start_time > max_runtime:
                raise TimeoutError("Script runtime exceeded 10 minutes")
            
            # OPTIMIZED: Only fetch connected IDs for reconnection tracking
            logger.info("Step 2: Fetching connected account IDs for reconnection tracking...")
            connected_ids = self.api.fetch_connected_account_ids()
            
            # Check timeout
            if time.time() - start_time > max_runtime:
                raise TimeoutError("Script runtime exceeded 10 minutes")
            
            logger.info(f"Summary: {len(disconnected)} disconnected, {len(connected_ids)} connected")
            
            # Record disconnections and get newly disconnected
            if is_first_run:
                # On first run, all disconnected accounts are "new"
                newly_disconnected = disconnected
                logger.info(f"First run: recording all {len(disconnected)} disconnected accounts")
                
                # Use bulk recording for first run
                if disconnected:
                    # Pass all at once for bulk insert
                    self.db.record_disconnections(disconnected, check_run_id)
                    logger.info("All disconnections recorded successfully")
            else:
                # Normal run - incremental check
                newly_disconnected = self.db.record_disconnections(disconnected, check_run_id)
                logger.info(f"Found {len(newly_disconnected)} newly disconnected accounts")
            
            # Resolve reconnections
            self.db.resolve_reconnections(connected_ids)
            
            # Log to CSV
            if newly_disconnected:
                self.csv_logger.log_disconnections(newly_disconnected, check_run_id)
            
            # Send Slack notification
            self.slack.send_disconnection_alert(newly_disconnected, check_run_id)
            
            # Clean up old records
            self.db.cleanup_old_records(Config.RETENTION_DAYS)
            
            # Update state
            state['last_check'] = datetime.now().isoformat()
            state['last_run_id'] = check_run_id
            state['total_disconnected'] = len(disconnected)
            state['total_connected'] = len(connected_ids)
            state['newly_disconnected'] = len(newly_disconnected)
            state['runtime_seconds'] = int(time.time() - start_time)
            self.state_manager.save_state(state)
            
            logger.info(f"Check completed in {int(time.time() - start_time)} seconds. New disconnections: {len(newly_disconnected)}")
            
        except TimeoutError as e:
            logger.error(f"Timeout error: {e}")
            self.slack.send_error_notification(str(e), check_run_id)
            raise
        except Exception as e:
            logger.error(f"Error during check: {e}", exc_info=True)
            self.slack.send_error_notification(str(e), check_run_id)
            raise

def main():
    """Main entry point"""
    # Check required environment variables
    if not Config.SMARTLEAD_BEARER_TOKEN:
        logger.error("SMARTLEAD_BEARER_TOKEN environment variable not set")
        sys.exit(1)
    
    if not Config.SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN environment variable not set")
        sys.exit(1)
    
    if not Config.SLACK_CHANNEL_ID:
        logger.error("SLACK_CHANNEL_ID environment variable not set")
        sys.exit(1)
    
    # Determine if this is the first run
    is_first_run = '--first-run' in sys.argv
    
    # Run monitor
    monitor = SmartleadMonitor()
    monitor.run_check(is_first_run=is_first_run)

if __name__ == "__main__":
    main()
