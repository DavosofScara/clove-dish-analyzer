# Upload Flow Runbook

Complete guide for the manual CSV/XLSX file upload and processing workflow.

**Last Updated:** January 2025  
**Maintained By:** Documentation Team

## Overview

The upload flow allows users to manually upload sales data files (CSV or XLSX) through the web interface. The system validates, transforms, and stores the data, then generates insights.

**Duration**: 30 seconds - 5 minutes (depending on file size)  
**User Impact**: High (primary data entry method)  
**Automation**: Manual trigger, automated processing

## Architecture

### Flow Diagram

```
User → Frontend → Backend API → ETL Service → Database → Insights Engine
  ↓        ↓          ↓              ↓             ↓            ↓
Upload → Validate → Parse → Transform → Store → Generate → Display
```

### Components

1. **Frontend**: Upload UI (`apps/web-sales/src/app/upload`)
2. **Backend API**: Upload endpoint (`backend/app/api/endpoints/upload.py`)
3. **ETL Service**: Data processor (`backend/app/services/etl.py`)
4. **Database**: PostgreSQL (sales_records, sales_imports tables)
5. **Insights Engine**: Analytics generator (`backend/app/services/insights_engine.py`)

## Step-by-Step Process

### Step 1: File Upload (Frontend)

**Location**: `apps/web-sales/src/app/upload/page.tsx`

```typescript
// User selects file
const handleFileSelect = (file: File) => {
  // Validate file type
  if (!file.name.endsWith('.csv') && !file.name.endsWith('.xlsx')) {
    throw new Error('Invalid file type');
  }
  
  // Validate file size (max 10MB)
  if (file.size > 10 * 1024 * 1024) {
    throw new Error('File too large');
  }
  
  // Upload to backend
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch(`${API_URL}/api/v1/upload/csv`, {
    method: 'POST',
    body: formData,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
};
```

**What to Monitor**:
- File size validation
- Network upload progress
- API response status

### Step 2: File Receipt (Backend API)

**Location**: `backend/app/api/endpoints/upload.py`

```python
@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate file extension
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Save file temporarily
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Create import record
    import_record = SalesImport(
        filename=file.filename,
        source="manual_upload",
        status="processing",
        user_id=current_user.id
    )
    db.add(import_record)
    db.commit()
    
    # Trigger ETL process
    result = await etl_service.process_file(file_path, import_record.id)
    
    return {"import_id": import_record.id, "status": "processing"}
```

**What to Monitor**:
- File write success
- Database insert success
- ETL trigger success

### Step 3: Data Parsing (ETL Service)

**Location**: `backend/app/services/etl.py`

```python
class ETLService:
    def process_file(self, file_path: str, import_id: str):
        try:
            # Step 3a: Parse file
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith('.xlsx'):
                df = pd.read_excel(file_path)
            
            # Step 3b: Detect columns
            column_mapping = self.detect_columns(df)
            
            # Step 3c: Validate data
            validation_result = self.validate_data(df, column_mapping)
            
            if validation_result.has_errors:
                return self.handle_validation_errors(validation_result)
            
            # Step 3d: Transform data
            transformed_data = self.transform_data(df, column_mapping)
            
            # Step 3e: Store in database
            self.store_data(transformed_data, import_id)
            
            # Step 3f: Trigger insights generation
            self.generate_insights(import_id)
            
            return {"status": "success", "records": len(transformed_data)}
            
        except Exception as e:
            logger.error(f"ETL error: {e}")
            return {"status": "error", "message": str(e)}
```

**What to Monitor**:
- Parsing errors
- Column detection accuracy
- Validation failures
- Transform success rate

### Step 4: Column Detection

**Location**: `backend/app/services/etl.py`

The system intelligently maps column names to expected fields:

```python
def detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
    """
    Detects column mappings from various formats
    Supports: English, Dutch, French, Spanish, German
    """
    
    COLUMN_PATTERNS = {
        'date': ['date', 'datum', 'fecha', 'data', 'transaction_date'],
        'product': ['product', 'item', 'artikel', 'producto', 'artigo'],
        'quantity': ['quantity', 'qty', 'aantal', 'cantidad', 'quantité'],
        'price': ['price', 'unit_price', 'prijs', 'precio', 'preço'],
        'total': ['total', 'amount', 'bedrag', 'montant'],
        'category': ['category', 'categorie', 'categoria'],
        'sku': ['sku', 'code', 'artikelnummer']
    }
    
    detected = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        for field, patterns in COLUMN_PATTERNS.items():
            if any(pattern in col_lower for pattern in patterns):
                detected[field] = col
                break
    
    return detected
```

**What to Monitor**:
- Detection success rate
- Unmapped columns
- Ambiguous mappings

### Step 5: Data Validation

**Location**: `backend/app/services/etl.py`

```python
def validate_data(self, df: pd.DataFrame, mapping: Dict) -> ValidationResult:
    errors = []
    warnings = []
    
    # Required fields check
    required_fields = ['date', 'product', 'quantity']
    for field in required_fields:
        if field not in mapping:
            errors.append(f"Required field '{field}' not found")
    
    # Data type validation
    if 'date' in mapping:
        try:
            pd.to_datetime(df[mapping['date']])
        except:
            errors.append("Invalid date format")
    
    if 'quantity' in mapping:
        if not pd.api.types.is_numeric_dtype(df[mapping['quantity']]):
            errors.append("Quantity must be numeric")
    
    # Business logic validation
    if 'price' in mapping:
        negative_prices = df[df[mapping['price']] < 0]
        if len(negative_prices) > 0:
            warnings.append(f"{len(negative_prices)} records with negative prices")
    
    # Duplicate check
    if 'transaction_id' in mapping:
        duplicates = df[df[mapping['transaction_id']].duplicated()]
        if len(duplicates) > 0:
            warnings.append(f"{len(duplicates)} duplicate transactions")
    
    return ValidationResult(errors=errors, warnings=warnings)
```

**What to Monitor**:
- Validation error types
- Error frequency
- Data quality trends

### Step 6: Data Transformation

**Location**: `backend/app/services/data_transformer.py`

```python
def transform_data(self, df: pd.DataFrame, mapping: Dict) -> List[SalesRecord]:
    records = []
    
    for _, row in df.iterrows():
        record = SalesRecord(
            transaction_id=self.generate_id(row, mapping),
            transaction_date=self.parse_date(row, mapping),
            product_name=row[mapping['product']],
            quantity=float(row[mapping['quantity']]),
            unit_price=self.calculate_price(row, mapping),
            total_amount=self.calculate_total(row, mapping),
            category=row.get(mapping.get('category'), 'Uncategorized'),
            raw_data=row.to_dict()
        )
        records.append(record)
    
    return records
```

**What to Monitor**:
- Transform success rate
- Data completeness
- Calculated fields accuracy

### Step 7: Database Storage

**Location**: `backend/app/services/etl.py`

```python
def store_data(self, records: List[SalesRecord], import_id: str):
    try:
        # Batch insert for performance
        db.bulk_insert_mappings(SalesRecord, records)
        db.commit()
        
        # Update import record
        import_record = db.query(SalesImport).filter_by(id=import_id).first()
        import_record.status = "completed"
        import_record.total_records = len(records)
        import_record.processed_records = len(records)
        import_record.completed_at = datetime.now()
        db.commit()
        
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
```

**What to Monitor**:
- Insert performance
- Database errors
- Transaction rollbacks

### Step 8: Insights Generation

**Location**: `backend/app/services/insights_engine.py`

```python
def generate_insights(self, import_id: str):
    # Get newly imported data
    records = db.query(SalesRecord).filter_by(import_id=import_id).all()
    
    # Run insights analyzers
    insights = []
    insights.extend(self.analyze_trends(records))
    insights.extend(self.detect_anomalies(records))
    insights.extend(self.generate_recommendations(records))
    
    # Store insights
    for insight in insights:
        db.add(insight)
    db.commit()
```

**What to Monitor**:
- Insights generated count
- Insight quality
- Generation performance

## Monitoring

### Key Metrics

```bash
# Check recent uploads
curl https://api.clove.solutions/api/v1/upload/status | jq '.recent_uploads'

# Check processing queue
curl https://api.clove.solutions/api/v1/upload/queue | jq '.pending'
```

### Database Queries

```sql
-- Recent uploads
SELECT 
    filename, 
    status, 
    total_records, 
    created_at
FROM sales_imports
ORDER BY created_at DESC
LIMIT 10;

-- Upload success rate (last 24h)
SELECT 
    status,
    COUNT(*) as count
FROM sales_imports
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;

-- Average processing time
SELECT 
    AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_seconds
FROM sales_imports
WHERE status = 'completed'
    AND created_at > NOW() - INTERVAL '7 days';
```

### Logs to Watch

```bash
# Backend logs
tail -f backend/logs/etl.log | grep "upload"

# Fly.io logs
flyctl logs --app=clove-api | grep "upload"
```

## Troubleshooting

### Issue: Upload Fails Immediately

**Symptoms**: User sees error right after selecting file

**Causes**:
- File too large (>10MB)
- Invalid file type
- Network error

**Solution**:
```bash
# Check file size limits
grep MAX_UPLOAD_SIZE backend/app/config.py

# Check allowed extensions
grep ALLOWED_EXTENSIONS backend/app/api/endpoints/upload.py
```

### Issue: Processing Stalls

**Symptoms**: Upload shows "processing" for > 5 minutes

**Causes**:
- Large file (>100K rows)
- Database connection issues
- Memory limits

**Solution**:
```bash
# Check processing status
flyctl ssh console --app=clove-api
ps aux | grep etl

# Check memory usage
free -h

# Restart if needed
flyctl apps restart clove-api
```

### Issue: Column Detection Fails

**Symptoms**: "Required field not found" error

**Causes**:
- Non-standard column names
- Different language
- Typos in headers

**Solution**:
1. Check column patterns in `etl.py`
2. Add new patterns if needed
3. Provide manual column mapping UI

### Issue: Validation Errors

**Symptoms**: "Data validation failed" message

**Causes**:
- Invalid dates
- Negative values
- Missing required data

**Solution**:
```python
# Check validation logs
tail -f backend/logs/validation.log

# Review error details
SELECT error_message, COUNT(*) 
FROM import_errors 
WHERE import_id = 'xxx'
GROUP BY error_message;
```

### Issue: No Insights Generated

**Symptoms**: Upload completes but no insights appear

**Causes**:
- Insufficient data points
- Date range too short
- Insights engine error

**Solution**:
```bash
# Check insights generation logs
tail -f backend/logs/insights.log

# Manually trigger insights
curl -X POST https://api.clove.solutions/api/v1/insights/generate \
  -H "Authorization: Bearer $TOKEN"
```

## Performance Optimization

### For Large Files

- Enable streaming upload
- Process in chunks
- Use background jobs

### For Frequent Uploads

- Implement upload queue
- Add rate limiting
- Cache column mappings

### For Better UX

- Show real-time progress
- Provide preview before processing
- Allow cancellation

## Testing

### Unit Tests

```bash
cd backend
pytest tests/test_etl.py::test_upload_flow
```

### Integration Tests

```bash
# Test full upload flow
pytest tests/test_api_upload.py::test_complete_upload
```

### Manual Testing

```bash
# Upload test file
curl -X POST http://localhost:8000/api/v1/upload/csv \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_data.csv"
```

## Related Documentation

- [API Reference - Upload](/docs/api/upload)
- [ETL Service Architecture](/docs/architecture/etl)
- [Insights Engine](/docs/runbooks/insights-generation)

---

**Last Updated:** January 2025  
**Maintained By:** Documentation Team

