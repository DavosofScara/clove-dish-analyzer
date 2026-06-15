# Dropbox Polling Runbook

Complete guide for the automated Dropbox folder monitoring and file import process.

## Overview

The Dropbox polling process automatically monitors a designated Dropbox folder for new sales data files (CSV/XLSX), downloads them, and processes them through the ETL pipeline.

**Frequency**: Every 15 minutes (configurable)  
**Duration**: 30 seconds - 2 minutes per check  
**User Impact**: Low (background process)  
**Automation**: Fully automated polling service

## Architecture

### Flow Diagram

```
Scheduler → Dropbox Service → Dropbox API → File Detection
    ↓           ↓                  ↓              ↓
Trigger → Authenticate → List Files → Check New → Download
                                                     ↓
                                            ETL Service → Database
```

### Components

1. **Scheduler**: APScheduler (`backend/app/scheduler/jobs.py`)
2. **Dropbox Service**: API client (`backend/app/services/dropbox_connector.py`)
3. **ETL Service**: Data processor (`backend/app/services/etl.py`)
4. **Database**: PostgreSQL (sales_records, dropbox_sync_state tables)
5. **File Storage**: Temporary local storage for processing

## Prerequisites

### Dropbox Setup

1. **Create Dropbox App**
   - Go to https://www.dropbox.com/developers/apps
   - Choose "Scoped access" app type
   - Select "Full Dropbox" or "App folder" access
   - Name your app (e.g., "Clove Sales Analyzer")

2. **Configure Permissions**
   Required scopes:
   - `files.content.read` - Read file contents
   - `files.metadata.read` - Read file/folder metadata

3. **Generate Access Token**
   - Go to app settings → OAuth 2
   - Generate access token (expires in 4 hours for short-lived)
   - OR implement OAuth flow for refresh tokens

4. **Environment Variables**
   ```env
   DROPBOX_ACCESS_TOKEN=sl.xxx
   DROPBOX_REFRESH_TOKEN=xxx (for long-term access)
   DROPBOX_APP_KEY=xxx
   DROPBOX_APP_SECRET=xxx
   DROPBOX_FOLDER_PATH=/sales_data
   DROPBOX_POLL_INTERVAL_MINUTES=15
   ```

### Folder Structure

Recommended Dropbox folder organization:

```
/sales_data/
  ├── incoming/           # New files to process
  ├── processed/          # Successfully processed files (moved here)
  ├── errors/             # Files that failed processing
  └── archive/            # Old files for retention
```

## Step-by-Step Process

### Step 1: Schedule Configuration

**Location**: `backend/app/scheduler/jobs.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()

def start_scheduler():
    # Dropbox polling job
    poll_interval = settings.DROPBOX_POLL_INTERVAL_MINUTES
    
    scheduler.add_job(
        poll_dropbox_folder,
        trigger=IntervalTrigger(minutes=poll_interval),
        id='dropbox_poller',
        replace_existing=True,
        max_instances=1  # Prevent overlapping runs
    )
    
    scheduler.start()
    logger.info(f"Dropbox poller started: checking every {poll_interval} minutes")
```

**Configuration**:
```env
DROPBOX_POLL_INTERVAL_MINUTES=15
DROPBOX_FOLDER_PATH=/sales_data/incoming
```

**What to Monitor**:
- Scheduler status
- Job execution frequency
- Overlapping runs (should be prevented)

### Step 2: Dropbox Authentication

**Location**: `backend/app/services/dropbox_connector.py`

```python
import dropbox
from dropbox.exceptions import AuthError, ApiError

class DropboxService:
    def __init__(self):
        self.access_token = settings.DROPBOX_ACCESS_TOKEN
        self.refresh_token = settings.DROPBOX_REFRESH_TOKEN
        self.app_key = settings.DROPBOX_APP_KEY
        self.app_secret = settings.DROPBOX_APP_SECRET
        self.folder_path = settings.DROPBOX_FOLDER_PATH
        
        self.dbx = self._get_client()
    
    def _get_client(self):
        """Initialize Dropbox client with auth"""
        try:
            if self.refresh_token:
                # Use refresh token for long-term access
                return dropbox.Dropbox(
                    oauth2_refresh_token=self.refresh_token,
                    app_key=self.app_key,
                    app_secret=self.app_secret
                )
            else:
                # Use access token (expires in 4 hours)
                return dropbox.Dropbox(self.access_token)
        except AuthError as e:
            logger.error(f"Dropbox auth failed: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """Test Dropbox connection"""
        try:
            account = self.dbx.users_get_current_account()
            logger.info(f"Connected to Dropbox: {account.name.display_name}")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
```

**What to Monitor**:
- Auth token expiration
- Connection failures
- API rate limits

### Step 3: File Detection

**Location**: `backend/app/services/dropbox_connector.py`

```python
async def list_new_files(self) -> List[str]:
    """
    List new files in Dropbox folder that haven't been processed
    """
    try:
        # Get list of files in folder
        result = self.dbx.files_list_folder(
            self.folder_path,
            recursive=False
        )
        
        all_files = result.entries
        
        # Handle pagination
        while result.has_more:
            result = self.dbx.files_list_folder_continue(result.cursor)
            all_files.extend(result.entries)
        
        # Filter for CSV/XLSX files only
        data_files = [
            f for f in all_files
            if isinstance(f, dropbox.files.FileMetadata) and
            (f.name.endswith('.csv') or f.name.endswith('.xlsx'))
        ]
        
        # Check which files we've already processed
        processed_ids = self._get_processed_file_ids()
        
        new_files = [
            f for f in data_files
            if f.id not in processed_ids
        ]
        
        logger.info(f"Found {len(new_files)} new files to process")
        return new_files
        
    except ApiError as e:
        logger.error(f"Error listing files: {e}")
        raise
```

**What to Monitor**:
- File count trends
- File size distribution
- Naming patterns

### Step 4: State Management

**Location**: `backend/app/services/dropbox_connector.py`

```python
def _get_processed_file_ids(self) -> Set[str]:
    """Get set of already processed file IDs from database"""
    
    processed = db.query(DropboxSyncState.file_id).filter(
        DropboxSyncState.status == 'processed'
    ).all()
    
    return {r[0] for r in processed}

def _mark_file_processed(
    self, 
    file_id: str, 
    file_name: str, 
    status: str,
    import_id: str = None,
    error_message: str = None
):
    """Mark file as processed in database"""
    
    sync_state = DropboxSyncState(
        file_id=file_id,
        file_name=file_name,
        status=status,
        import_id=import_id,
        error_message=error_message,
        processed_at=datetime.now()
    )
    
    db.add(sync_state)
    db.commit()
```

**What to Monitor**:
- State table size
- Processing status distribution
- Duplicate prevention

### Step 5: File Download

**Location**: `backend/app/services/dropbox_connector.py`

```python
async def download_file(self, file_metadata) -> str:
    """
    Download file from Dropbox to local temp storage
    
    Returns: Local file path
    """
    try:
        # Create temp directory
        temp_dir = "temp_downloads"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Generate local file path
        local_path = os.path.join(
            temp_dir, 
            f"{file_metadata.id}_{file_metadata.name}"
        )
        
        # Download file
        logger.info(f"Downloading: {file_metadata.name}")
        
        metadata, response = self.dbx.files_download(file_metadata.path_display)
        
        with open(local_path, "wb") as f:
            f.write(response.content)
        
        logger.info(f"Downloaded {len(response.content)} bytes to {local_path}")
        
        return local_path
        
    except ApiError as e:
        logger.error(f"Download failed: {e}")
        raise
```

**What to Monitor**:
- Download success rate
- Download speeds
- Temp storage usage

### Step 6: File Processing

**Location**: `backend/app/services/dropbox_connector.py`

```python
async def process_file(self, file_metadata) -> Dict:
    """Download and process a file"""
    
    try:
        # Download file
        local_path = await self.download_file(file_metadata)
        
        # Create import record
        import_record = SalesImport(
            filename=file_metadata.name,
            source="dropbox_sync",
            status="processing",
            metadata={"dropbox_id": file_metadata.id}
        )
        db.add(import_record)
        db.commit()
        
        # Process through ETL
        etl_service = ETLService()
        result = await etl_service.process_file(local_path, import_record.id)
        
        # Mark as processed
        self._mark_file_processed(
            file_id=file_metadata.id,
            file_name=file_metadata.name,
            status='processed',
            import_id=import_record.id
        )
        
        # Move to processed folder in Dropbox
        await self.move_to_processed(file_metadata)
        
        # Clean up local file
        os.remove(local_path)
        
        logger.info(f"Successfully processed: {file_metadata.name}")
        return {"status": "success", "records": result['records']}
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        
        # Mark as error
        self._mark_file_processed(
            file_id=file_metadata.id,
            file_name=file_metadata.name,
            status='error',
            error_message=str(e)
        )
        
        # Move to error folder
        await self.move_to_error(file_metadata)
        
        return {"status": "error", "message": str(e)}
```

**What to Monitor**:
- Processing success rate
- Processing time per file
- Error types and frequency

### Step 7: File Organization

**Location**: `backend/app/services/dropbox_connector.py`

```python
async def move_to_processed(self, file_metadata):
    """Move file to processed folder"""
    try:
        from_path = file_metadata.path_display
        to_path = f"/sales_data/processed/{file_metadata.name}"
        
        self.dbx.files_move_v2(from_path, to_path, autorename=True)
        logger.info(f"Moved to processed: {file_metadata.name}")
    except Exception as e:
        logger.warning(f"Could not move file: {e}")

async def move_to_error(self, file_metadata):
    """Move file to error folder"""
    try:
        from_path = file_metadata.path_display
        to_path = f"/sales_data/errors/{file_metadata.name}"
        
        self.dbx.files_move_v2(from_path, to_path, autorename=True)
        logger.info(f"Moved to errors: {file_metadata.name}")
    except Exception as e:
        logger.warning(f"Could not move file: {e}")
```

**What to Monitor**:
- File movement success
- Folder organization
- Autorename conflicts

### Step 8: Main Polling Loop

**Location**: `backend/app/scheduler/jobs.py`

```python
async def poll_dropbox_folder():
    """Main polling function called by scheduler"""
    
    logger.info("Starting Dropbox poll...")
    
    try:
        service = DropboxService()
        
        # Test connection
        if not await service.test_connection():
            raise Exception("Dropbox connection failed")
        
        # Get new files
        new_files = await service.list_new_files()
        
        if not new_files:
            logger.info("No new files found")
            return
        
        logger.info(f"Processing {len(new_files)} new files")
        
        # Process each file
        results = []
        for file in new_files:
            result = await service.process_file(file)
            results.append(result)
        
        # Summary
        successful = len([r for r in results if r['status'] == 'success'])
        failed = len([r for r in results if r['status'] == 'error'])
        
        # Notification
        await send_notification(
            channel="#clove-ops",
            message=f"📁 Dropbox poll complete: {successful} processed, {failed} failed"
        )
        
    except Exception as e:
        logger.error(f"Poll failed: {e}")
        await send_notification(
            channel="#clove-incidents",
            message=f"❌ Dropbox poll failed: {str(e)}"
        )
```

**What to Monitor**:
- Poll completion time
- Success/failure ratios
- Alert notifications

## Monitoring

### Check Polling Status

```bash
# View recent polls
curl https://api.clove.solutions/api/v1/integrations/dropbox/status \
  -H "Authorization: Bearer $TOKEN" | jq

# Expected response:
{
  "last_poll": "2025-10-10T14:15:00Z",
  "files_processed": 3,
  "next_poll": "2025-10-10T14:30:00Z",
  "status": "active"
}
```

### Database Queries

```sql
-- Recent Dropbox syncs
SELECT 
    file_name,
    status,
    processed_at,
    error_message
FROM dropbox_sync_state
ORDER BY processed_at DESC
LIMIT 20;

-- Success rate (last 24h)
SELECT 
    status,
    COUNT(*) as count
FROM dropbox_sync_state
WHERE processed_at > NOW() - INTERVAL '24 hours'
GROUP BY status;

-- Files by hour
SELECT 
    DATE_TRUNC('hour', processed_at) as hour,
    COUNT(*) as files
FROM dropbox_sync_state
WHERE processed_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour DESC;
```

### Application Logs

```bash
# Watch Dropbox logs
flyctl logs --app=clove-api | grep "dropbox"

# Tail sync logs
flyctl ssh console --app=clove-api
tail -f /app/logs/dropbox_sync.log
```

## Manual Operations

### Trigger Manual Poll

```bash
curl -X POST https://api.clove.solutions/api/v1/integrations/dropbox/poll \
  -H "Authorization: Bearer $TOKEN"
```

### List Files in Folder

```bash
curl https://api.clove.solutions/api/v1/integrations/dropbox/files \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Reprocess Failed File

```bash
curl -X POST https://api.clove.solutions/api/v1/integrations/dropbox/reprocess \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"file_id": "id:xxx"}'
```

## Troubleshooting

### Issue: No Files Being Detected

**Symptoms**: Polls complete but 0 files found

**Solutions**:
1. Check folder path configuration
2. Verify files are in correct format (.csv/.xlsx)
3. Check file permissions

```bash
# Test folder access
curl https://api.clove.solutions/api/v1/integrations/dropbox/test \
  -H "Authorization: Bearer $TOKEN"

# List all files
curl https://api.clove.solutions/api/v1/integrations/dropbox/files?folder=/sales_data \
  -H "Authorization: Bearer $TOKEN"
```

### Issue: Files Processed Multiple Times

**Symptoms**: Duplicate records from same file

**Solutions**:
```sql
-- Check for duplicate processing
SELECT file_id, COUNT(*)
FROM dropbox_sync_state
GROUP BY file_id
HAVING COUNT(*) > 1;

-- Reset state if needed
DELETE FROM dropbox_sync_state WHERE file_id = 'xxx';
```

### Issue: Authentication Expired

**Symptoms**: "401 Unauthorized" errors

**Solutions**:
```bash
# Refresh access token (if using OAuth)
curl -X POST https://api.dropbox.com/oauth2/token \
  -d grant_type=refresh_token \
  -d refresh_token=$REFRESH_TOKEN \
  -u "$APP_KEY:$APP_SECRET"

# Update secrets
flyctl secrets set DROPBOX_ACCESS_TOKEN=new-token --app=clove-api
```

### Issue: Download Failures

**Symptoms**: Files detected but download fails

**Solutions**:
1. Check network connectivity
2. Verify file size limits
3. Check temp storage space

```bash
# Check disk space
flyctl ssh console --app=clove-api
df -h
du -sh temp_downloads/
```

### Issue: Processing Stalls

**Symptoms**: Files downloaded but ETL doesn't complete

**Solutions**:
1. Check ETL service logs
2. Verify database connection
3. Review file format

```bash
# Check processing queue
flyctl ssh console --app=clove-api
ps aux | grep python
```

## Performance Optimization

### For High Volume

```python
# Process files in parallel
async def process_files_parallel(files):
    tasks = [process_file(f) for f in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### For Large Files

```python
# Stream download for large files
async def download_large_file(file_metadata):
    chunk_size = 4 * 1024 * 1024  # 4MB chunks
    # Implement chunked download
```

### For Frequent Polls

```python
# Use cursor-based pagination
# Store last modification time
# Only check for new/modified files
```

## Testing

```bash
# Test connection
pytest backend/tests/test_dropbox.py::test_connection

# Test file detection
pytest backend/tests/test_dropbox.py::test_list_files

# Test full process
pytest backend/tests/test_dropbox.py::test_process_file
```

## Related Documentation

- [Dropbox API Documentation](https://www.dropbox.com/developers/documentation)
- [Upload Flow Runbook](/docs/runbooks/upload-flow)
- [ETL Architecture](/docs/architecture/etl)

---

**Last Updated**: October 10, 2025  
**Maintained By**: DevOps Team

