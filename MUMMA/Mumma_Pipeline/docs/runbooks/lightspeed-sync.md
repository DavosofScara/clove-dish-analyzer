# Lightspeed Sync Runbook

Complete guide for the automated Lightspeed POS data synchronization process.

## Overview

The Lightspeed sync process automatically retrieves sales data from Lightspeed POS API and imports it into Clove Sales Analyzer. This can run on demand or on a schedule.

**Frequency**: Nightly at 2:00 AM (configurable)  
**Duration**: 2-10 minutes (depending on data volume)  
**User Impact**: Low (background process)  
**Automation**: Fully automated with scheduler

## Architecture

### Flow Diagram

```
Scheduler → Backend API → Lightspeed Service → Lightspeed API
    ↓           ↓               ↓                   ↓
Schedule → Trigger → Authenticate → Fetch Data → Transform
                                         ↓
                                    ETL Service → Database → Insights
```

### Components

1. **Scheduler**: APScheduler (`backend/app/scheduler/jobs.py`)
2. **Lightspeed Service**: API client (`backend/app/services/lightspeed.py`)
3. **ETL Service**: Data transformer (`backend/app/services/etl.py`)
4. **Database**: PostgreSQL (sales_records table)
5. **Insights Engine**: Analytics generator

## Prerequisites

### Lightspeed API Access

1. **Account Setup**
   - Active Lightspeed POS subscription
   - API access enabled
   - Account ID from Lightspeed

2. **API Credentials**
   ```env
   LIGHTSPEED_API_KEY=your-api-key-here
   LIGHTSPEED_API_URL=https://api.lightspeedapp.com/API
   LIGHTSPEED_ACCOUNT_ID=123456
   ```

3. **API Permissions**
   - `Account`: Read
   - `Sale`: Read
   - `SaleLine`: Read
   - `Item`: Read

### Rate Limits

- **Bucket Limit**: 10 requests per second
- **Daily Limit**: 10,000 requests per day
- **Burst Limit**: 180 requests per minute

## Step-by-Step Process

### Step 1: Schedule Configuration

**Location**: `backend/app/scheduler/jobs.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings

scheduler = AsyncIOScheduler()

def start_scheduler():
    # Nightly data refresh
    scheduler.add_job(
        sync_lightspeed_data,
        trigger='cron',
        hour=settings.NIGHTLY_REFRESH_HOUR,  # Default: 2 AM
        minute=settings.NIGHTLY_REFRESH_MINUTE,  # Default: 0
        id='lightspeed_nightly_sync',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started: Lightspeed sync scheduled")
```

**Configuration**:
```env
NIGHTLY_REFRESH_HOUR=2
NIGHTLY_REFRESH_MINUTE=0
```

**What to Monitor**:
- Scheduler running status
- Job execution history
- Missed job alerts

### Step 2: Sync Initiation

**Location**: `backend/app/services/lightspeed.py`

```python
class LightspeedService:
    def __init__(self):
        self.api_key = settings.LIGHTSPEED_API_KEY
        self.api_url = settings.LIGHTSPEED_API_URL
        self.account_id = settings.LIGHTSPEED_ACCOUNT_ID
        
    async def sync_data(self, days_back: int = 7):
        """
        Sync sales data from Lightspeed
        
        Args:
            days_back: Number of days to sync (default: 7)
        """
        try:
            logger.info(f"Starting Lightspeed sync: {days_back} days")
            
            # Step 2a: Test connection
            await self.test_connection()
            
            # Step 2b: Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Step 2c: Fetch sales
            sales = await self.fetch_sales(start_date, end_date)
            
            # Step 2d: Process data
            result = await self.process_sales(sales)
            
            logger.info(f"Lightspeed sync completed: {result['records']} records")
            return result
            
        except Exception as e:
            logger.error(f"Lightspeed sync failed: {e}")
            raise
```

**What to Monitor**:
- Sync start time
- API connection success
- Date range calculations

### Step 3: API Authentication

**Location**: `backend/app/services/lightspeed.py`

```python
async def test_connection(self) -> bool:
    """Test Lightspeed API connection"""
    try:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.api_url}/Account/{self.account_id}.json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            
        if response.status_code == 200:
            logger.info("Lightspeed connection successful")
            return True
        else:
            logger.error(f"Connection failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise
```

**What to Monitor**:
- Authentication failures
- API key expiration
- Network timeouts

### Step 4: Data Fetching

**Location**: `backend/app/services/lightspeed.py`

```python
async def fetch_sales(
    self, 
    start_date: datetime, 
    end_date: datetime
) -> List[Dict]:
    """
    Fetch sales data from Lightspeed API with pagination
    """
    all_sales = []
    offset = 0
    limit = 100  # Max per page
    
    headers = {
        'Authorization': f'Bearer {self.api_key}',
        'Content-Type': 'application/json'
    }
    
    while True:
        # Build query parameters
        params = {
            'createTime': f'>={start_date.isoformat()},<{end_date.isoformat()}',
            'limit': limit,
            'offset': offset,
            'load_relations': '["SaleLines", "Customer"]'
        }
        
        url = f"{self.api_url}/Account/{self.account_id}/Sale.json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, 
                headers=headers, 
                params=params,
                timeout=30.0
            )
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code}")
        
        data = response.json()
        sales = data.get('Sale', [])
        
        if not sales:
            break  # No more data
        
        all_sales.extend(sales)
        offset += limit
        
        # Rate limiting
        await asyncio.sleep(0.1)  # 10 requests/second
        
        logger.info(f"Fetched {len(all_sales)} sales so far...")
    
    logger.info(f"Total sales fetched: {len(all_sales)}")
    return all_sales
```

**What to Monitor**:
- Pagination progress
- Rate limit compliance
- API response times
- Data completeness

### Step 5: Data Transformation

**Location**: `backend/app/services/lightspeed.py`

```python
async def process_sales(self, sales: List[Dict]) -> Dict:
    """Transform Lightspeed sales to our format"""
    transformed_records = []
    
    for sale in sales:
        # Extract sale lines (individual products)
        for line in sale.get('SaleLines', {}).get('SaleLine', []):
            record = {
                'transaction_id': f"{sale['saleID']}_{line['saleLineID']}",
                'transaction_date': sale['createTime'],
                'product_id': line.get('itemID'),
                'product_name': line.get('Item', {}).get('description', 'Unknown'),
                'category': line.get('Item', {}).get('Category', {}).get('name'),
                'sku': line.get('Item', {}).get('sku'),
                'quantity': float(line.get('unitQuantity', 1)),
                'unit_price': float(line.get('unitPrice', 0)),
                'total_amount': float(line.get('calcTotal', 0)),
                'cost': float(line.get('avgCost', 0)),
                'customer_id': sale.get('customerID'),
                'customer_name': sale.get('Customer', {}).get('firstName', '') + ' ' + 
                                 sale.get('Customer', {}).get('lastName', ''),
                'store_location': sale.get('Shop', {}).get('name', 'Main'),
                'raw_data': {'sale': sale, 'line': line}
            }
            
            transformed_records.append(record)
    
    # Create import record
    import_record = SalesImport(
        filename=f"lightspeed_sync_{datetime.now().isoformat()}",
        source="lightspeed_api",
        status="processing",
        total_records=len(transformed_records)
    )
    db.add(import_record)
    db.commit()
    
    # Store data using ETL service
    etl_service = ETLService()
    result = await etl_service.store_transformed_data(
        transformed_records, 
        import_record.id
    )
    
    return result
```

**What to Monitor**:
- Transformation success rate
- Data quality
- Missing fields
- Duplicate records

### Step 6: Deduplication

**Location**: `backend/app/services/etl.py`

```python
async def store_transformed_data(
    self, 
    records: List[Dict], 
    import_id: str
) -> Dict:
    """Store data with deduplication"""
    
    # Check for existing records
    existing_ids = set()
    transaction_ids = [r['transaction_id'] for r in records]
    
    existing = db.query(SalesRecord.transaction_id).filter(
        SalesRecord.transaction_id.in_(transaction_ids)
    ).all()
    
    existing_ids = {r[0] for r in existing}
    
    # Filter out duplicates
    new_records = [
        r for r in records 
        if r['transaction_id'] not in existing_ids
    ]
    
    logger.info(f"Inserting {len(new_records)} new records")
    logger.info(f"Skipping {len(records) - len(new_records)} duplicates")
    
    # Batch insert
    if new_records:
        db.bulk_insert_mappings(SalesRecord, new_records)
        db.commit()
    
    # Update import record
    import_record = db.query(SalesImport).filter_by(id=import_id).first()
    import_record.status = "completed"
    import_record.processed_records = len(new_records)
    import_record.completed_at = datetime.now()
    db.commit()
    
    # Trigger insights generation
    await self.generate_insights(import_id)
    
    return {
        "status": "success",
        "new_records": len(new_records),
        "duplicates": len(records) - len(new_records)
    }
```

**What to Monitor**:
- Duplicate detection accuracy
- Database insert performance
- Transaction commit success

### Step 7: Post-Sync Actions

**Location**: `backend/app/scheduler/jobs.py`

```python
async def sync_lightspeed_data():
    """Main sync function called by scheduler"""
    try:
        # Run sync
        service = LightspeedService()
        result = await service.sync_data(days_back=7)
        
        # Send success notification
        await send_notification(
            channel="#clove-ops",
            message=f"✅ Lightspeed sync completed: {result['new_records']} new records"
        )
        
        # Update sync status
        db.add(SyncLog(
            source="lightspeed",
            status="success",
            records_synced=result['new_records'],
            duration_seconds=result['duration']
        ))
        db.commit()
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        
        # Send error notification
        await send_notification(
            channel="#clove-incidents",
            message=f"❌ Lightspeed sync failed: {str(e)}"
        )
        
        # Update sync status
        db.add(SyncLog(
            source="lightspeed",
            status="failed",
            error_message=str(e)
        ))
        db.commit()
        
        raise
```

**What to Monitor**:
- Sync completion notifications
- Error alerts
- Sync log entries

## Monitoring

### Check Sync Status

```bash
# View recent syncs
curl https://api.clove.solutions/api/v1/integrations/lightspeed/status \
  -H "Authorization: Bearer $TOKEN" | jq

# Expected response:
{
  "last_sync": "2025-10-10T02:00:15Z",
  "status": "success",
  "records_synced": 1234,
  "next_sync": "2025-10-11T02:00:00Z"
}
```

### Database Queries

```sql
-- Check recent Lightspeed imports
SELECT 
    created_at,
    status,
    total_records,
    processed_records,
    EXTRACT(EPOCH FROM (completed_at - created_at)) as duration_seconds
FROM sales_imports
WHERE source = 'lightspeed_api'
ORDER BY created_at DESC
LIMIT 10;

-- Check for sync failures
SELECT 
    DATE(created_at) as sync_date,
    COUNT(*) as attempts,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
FROM sales_imports
WHERE source = 'lightspeed_api'
    AND created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY sync_date DESC;
```

### Application Logs

```bash
# Watch sync logs
flyctl logs --app=clove-api | grep "lightspeed"

# Check scheduler logs
flyctl ssh console --app=clove-api
tail -f /app/logs/scheduler.log
```

## Manual Sync

### Trigger On-Demand Sync

```bash
# Sync last 7 days
curl -X POST https://api.clove.solutions/api/v1/integrations/lightspeed/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'

# Sync specific date range
curl -X POST https://api.clove.solutions/api/v1/integrations/lightspeed/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-01",
    "end_date": "2025-10-10"
  }'
```

## Troubleshooting

### Issue: Authentication Fails

**Symptoms**: "401 Unauthorized" errors

**Solutions**:
```bash
# Test API key
curl -H "Authorization: Bearer $LIGHTSPEED_API_KEY" \
  "https://api.lightspeedapp.com/API/Account/$ACCOUNT_ID.json"

# Verify credentials in environment
flyctl secrets list --app=clove-api | grep LIGHTSPEED

# Rotate API key if needed
flyctl secrets set LIGHTSPEED_API_KEY=new-key --app=clove-api
```

### Issue: Rate Limit Exceeded

**Symptoms**: "429 Too Many Requests"

**Solutions**:
1. Reduce sync frequency
2. Implement exponential backoff
3. Contact Lightspeed for higher limits

```python
# Add retry logic with backoff
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def fetch_with_retry(url, headers):
    response = await client.get(url, headers=headers)
    if response.status_code == 429:
        raise Exception("Rate limited")
    return response
```

### Issue: Sync Takes Too Long

**Symptoms**: Sync duration > 15 minutes

**Solutions**:
1. Reduce `days_back` parameter
2. Implement chunked syncing
3. Optimize database inserts

```python
# Chunk large syncs
async def sync_in_chunks(days_back: int, chunk_days: int = 1):
    for i in range(0, days_back, chunk_days):
        start = datetime.now() - timedelta(days=i+chunk_days)
        end = datetime.now() - timedelta(days=i)
        await sync_data_range(start, end)
```

### Issue: Missing Data

**Symptoms**: Records in Lightspeed but not in Clove

**Solutions**:
```bash
# Check date range
# Verify load_relations parameter
# Check for API errors in logs

# Manual backfill
curl -X POST https://api.clove.solutions/api/v1/integrations/lightspeed/sync \
  -d '{"start_date": "2025-09-01", "end_date": "2025-10-01"}'
```

### Issue: Duplicate Records

**Symptoms**: Same sales appearing multiple times

**Solutions**:
```sql
-- Find duplicates
SELECT transaction_id, COUNT(*)
FROM sales_records
GROUP BY transaction_id
HAVING COUNT(*) > 1;

-- Remove duplicates
DELETE FROM sales_records
WHERE id NOT IN (
    SELECT MIN(id)
    FROM sales_records
    GROUP BY transaction_id
);
```

## Performance Optimization

### For Large Accounts

```python
# Implement pagination with cursor
# Use parallel fetching for different date ranges
# Cache product/customer lookups
```

### For Frequent Syncs

```python
# Use incremental syncing (only new sales)
# Implement change detection
# Store last sync timestamp
```

## Testing

```bash
# Test connection
pytest backend/tests/test_lightspeed.py::test_connection

# Test full sync
pytest backend/tests/test_lightspeed.py::test_sync_data

# Test with mock data
pytest backend/tests/test_lightspeed.py::test_transform_sales
```

## Related Documentation

- [Lightspeed API Documentation](https://developers.lightspeedhq.com/retail/introduction/introduction/)
- [API Integration Guide](/docs/api/integrations)
- [ETL Architecture](/docs/architecture/etl)

---

**Last Updated**: October 10, 2025  
**Maintained By**: DevOps Team

