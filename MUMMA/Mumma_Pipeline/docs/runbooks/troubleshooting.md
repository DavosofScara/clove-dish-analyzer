# Troubleshooting Guide

Common issues and solutions for Clove Sales Analyzer operations.

**Last Updated:** January 2025  
**Maintained By:** Documentation Team

---

## Quick Diagnostics

Run these commands first to diagnose common issues:

```bash
# Check API health
curl https://api.clove.solutions/health

# Check staging API health
curl https://clove-api-staging.fly.dev/health

# Check database connection (if you have access)
psql $DATABASE_URL -c "SELECT 1"

# View recent API logs
flyctl logs --app clove-api | tail -100

# View staging API logs
flyctl logs --app clove-api-staging | tail -100
```

---

## Common Issues

### Upload Failures

**Symptoms:**
- File upload fails immediately
- "Invalid file format" error
- "File too large" error
- Upload times out

**Diagnosis:**

```bash
# Check file format
file your_data.csv

# Check file size
ls -lh your_data.csv

# Test upload endpoint
curl -X POST https://api.clove.solutions/api/v1/ingest/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Org-Id: org_your_org" \
  -F "file=@your_data.csv"
```

**Solutions:**

1. **Invalid File Format**
   - Ensure file is CSV or XLSX
   - Check file extension matches content
   - Remove BOM (Byte Order Mark) from CSV if present

2. **File Too Large**
   - Maximum file size: 10MB
   - Split large files into smaller chunks
   - Consider using Lightspeed API integration for large datasets

3. **Upload Timeout**
   - Check network connection
   - Verify API endpoint is accessible
   - Try again with smaller file

4. **Column Detection Fails**
   - Review column headers in your file
   - Ensure required columns exist: Date, Product, Quantity
   - Check for typos in column names
   - See [Upload Flow Runbook](./upload-flow.md#step-4-column-detection) for supported formats

---

### Parse Failures

**Symptoms:**
- "Required field not found" error
- "Data validation failed" message
- Parse returns 0 valid rows

**Diagnosis:**

```bash
# Check parse endpoint with mapping
curl -X POST https://api.clove.solutions/api/v1/ingest/parse \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Org-Id: org_your_org" \
  -H "Content-Type: application/json" \
  -d '{
    "uploadId": "upload_abc123",
    "columnMapping": {
      "date": "Date",
      "product_name": "Product",
      "quantity": "Quantity",
      "unit_price": "Price"
    }
  }'
```

**Solutions:**

1. **Required Field Not Found**
   - Verify column mapping is correct
   - Ensure Date, Product, and Quantity columns are mapped
   - Check for case sensitivity issues

2. **Data Validation Errors**
   - Review validation errors in parse response
   - Fix invalid dates (use YYYY-MM-DD or DD/MM/YYYY format)
   - Remove negative values where inappropriate
   - Fill in missing required data

3. **Zero Valid Rows**
   - Check that column mapping matches your file headers
   - Verify data types are correct (dates, numbers)
   - Review sample rows in upload response

---

### Commit Failures

**Symptoms:**
- "404: Organization not found" error
- Commit returns 500 error
- No data appears after commit

**Diagnosis:**

```bash
# Test commit endpoint
curl -X POST https://api.clove.solutions/api/v1/ingest/commit \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Org-Id: org_your_org" \
  -H "Content-Type: application/json" \
  -d '{
    "uploadId": "upload_abc123",
    "skipInvalidRows": true,
    "deduplicateBy": ["date", "product_name"]
  }'
```

**Solutions:**

1. **404: Organization not found**
   - **Root Cause:** Organization with `clerkId` doesn't exist in database
   - **Fix for Staging:**
     ```bash
     # Seed demo organization on staging
     cd api/fastapi
     python deploy_seed.py
     # Or manually create: org_demo_clove_bistro
     ```
   - **Fix for Production:**
     - Organization should auto-create on first API call
     - If not, verify Clerk webhook is working
     - Check organization ID matches Clerk organization ID

2. **Commit Returns 500 Error**
   - Check API logs: `flyctl logs --app clove-api`
   - Verify database connection is working
   - Ensure data was parsed successfully before commit
   - Check for database constraint violations

3. **No Data After Commit**
   - Verify commit returned success (inserted > 0)
   - Check sales summary endpoint: `/api/v1/sales/summary`
   - Ensure organization ID matches in all requests
   - Review commit response for skipped/duplicate warnings

---

### Sync Failures

**Symptoms:**
- Lightspeed sync doesn't work
- Data not appearing from external source
- API credentials invalid

**Solutions:**

1. **API Credentials Invalid**
   - Verify credentials in Settings page
   - Check credential format (no extra spaces)
   - Re-authenticate OAuth connection if needed

2. **Rate Limits**
   - Check API rate limit status
   - Wait for rate limit window to reset
   - Contact support if persistent

3. **Network Connectivity**
   - Verify external API is accessible
   - Check firewall rules allow outbound connections
   - Test API endpoint directly

---

### Performance Issues

**Symptoms:**
- Slow upload/parse times
- Dashboard loads slowly
- Charts take long to render

**Diagnosis:**

```bash
# Check API response times
time curl https://api.clove.solutions/health

# Check database query performance (if you have access)
psql $DATABASE_URL -c "EXPLAIN ANALYZE SELECT * FROM transactions LIMIT 100;"

# Monitor API logs for slow queries
flyctl logs --app clove-api | grep "slow"
```

**Solutions:**

1. **Slow Upload/Parse**
   - Large files take longer (1000+ rows)
   - Consider splitting files into smaller chunks
   - Use Lightspeed API for large datasets

2. **Slow Dashboard**
   - Check network connection
   - Verify database indexes are in place
   - Review dashboard query performance

3. **Slow Chart Rendering**
   - Reduce date range in filters
   - Check for too many data points
   - Verify chart library is up to date

---

### Data Quality Issues

**Symptoms:**
- Incorrect totals in reports
- Missing transactions
- Duplicate data appearing

**Solutions:**

1. **Incorrect Totals**
   - Verify source data is correct
   - Check for data transformation errors
   - Review column mapping for revenue/price fields

2. **Missing Transactions**
   - Check commit response for skipped rows
   - Review validation errors during parse
   - Verify date range in queries

3. **Duplicate Data**
   - Check `deduplicateBy` settings in commit
   - Review transaction IDs for duplicates
   - Use deduplication on commit: `deduplicateBy: ["date", "product_name"]`

---

## Emergency Procedures

### Service Down

**Symptoms:**
- API returns 503/500 errors
- Health check fails
- All requests time out

**Steps:**

1. Check status page (if available)
2. Review error logs:
   ```bash
   flyctl logs --app clove-api --region all | tail -200
   ```
3. Check Fly.io status: https://status.fly.io
4. Restart application if needed:
   ```bash
   flyctl apps restart clove-api
   ```
5. Escalate to on-call engineer if unresolved

### Data Corruption

**Symptoms:**
- Data appears incorrect or missing
- Reports show impossible values
- Database queries fail

**Steps:**

1. **Stop all imports immediately**
   - Disable auto-sync if enabled
   - Prevent new uploads

2. **Identify affected records**
   ```bash
   # Check recent transactions (if you have DB access)
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM transactions WHERE created_at > NOW() - INTERVAL '24 hours';"
   ```

3. **Restore from backup** (if available)
   ```bash
   # Contact DevOps for backup restoration
   # Check Supabase dashboard for point-in-time recovery
   ```

4. **Validate integrity**
   - Run data validation queries
   - Compare counts with source data
   - Verify relationships between tables

5. **Notify team**
   - Document issue in incident log
   - Notify affected users
   - Create post-mortem report

---

## Staging Environment Issues

### Staging Organization Missing

**Issue:** Staging E2E tests fail with "404: Organization not found"

**Solution:**

```bash
# Seed demo organization on staging
cd api/fastapi

# Set staging database URL
export DATABASE_URL="postgresql://...staging..."

# Run seed script
python deploy_seed.py

# Or create organization manually via API
curl -X POST https://clove-api-staging.fly.dev/api/v1/organizations \
  -H "Content-Type: application/json" \
  -d '{
    "clerkId": "org_demo_clove_bistro",
    "name": "Clove Demo Bistro"
  }'
```

### Staging Smoke Test Failures

**Run full smoke test:**

```bash
# From project root
chmod +x tools/smoke-staging.sh
STAGING_API=https://clove-api-staging.fly.dev bash tools/smoke-staging.sh
```

**Common failures:**
- Health endpoint: Check API is deployed
- CORS: Verify CORS_ORIGINS includes staging domain
- 404: Check route is registered in FastAPI

---

## Getting Help

### Support Channels

- **Internal Slack:** #clove-dev
- **Incidents:** #clove-incidents
- **On-Call:** Check #oncall channel
- **Escalation:** Engineering Manager

### What to Include in Support Requests

1. **Error message** (full text)
2. **Steps to reproduce**
3. **Expected vs actual behavior**
4. **Logs** (if available)
5. **Environment** (staging/production)
6. **Time of occurrence**

### Log Locations

- **API Logs:** `flyctl logs --app clove-api`
- **Staging Logs:** `flyctl logs --app clove-api-staging`
- **Frontend Logs:** Browser console (F12)
- **Database Logs:** Supabase dashboard (if available)

---

## Related Documentation

- [Upload Flow Runbook](./upload-flow.md) - Complete upload workflow
- [API Reference - Upload](../api/upload.md) - Upload API endpoints
- [Deployment Guide](../DEPLOYMENT.md) - Deployment troubleshooting

---

**Last Updated:** January 2025  
**Maintained By:** Documentation Team

