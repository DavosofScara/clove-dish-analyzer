# Runbooks Overview

Operational runbooks for managing and troubleshooting Clove Sales Analyzer.

## What are Runbooks?

Runbooks are step-by-step guides for common operational tasks and troubleshooting procedures. They help ensure consistent execution of important processes and quick resolution of issues.

## Available Runbooks

### Data Processing
- **[Upload Flow](/docs/runbooks/upload-flow)**: Manual CSV/XLSX file upload and processing
- **[Lightspeed Sync](/docs/runbooks/lightspeed-sync)**: Automated Lightspeed POS data synchronization
- **[Dropbox Polling](/docs/runbooks/dropbox-polling)**: Automated file polling from Dropbox folders

### Analytics
- **[Insights Generation](/docs/runbooks/insights-generation)**: How the insights engine works and generates recommendations

### Operations
- **[Troubleshooting](/docs/runbooks/troubleshooting)**: Common issues and their solutions

## When to Use These Runbooks

### For Developers
- Understanding how core features work
- Debugging data processing issues
- Adding new integrations
- Optimizing performance

### For DevOps
- Monitoring scheduled jobs
- Investigating production issues
- Scaling infrastructure
- Incident response

### For Support
- Helping customers with upload issues
- Diagnosing integration problems
- Understanding error messages
- Escalating technical issues

## Runbook Structure

Each runbook follows this format:

1. **Overview**: What the process does
2. **Architecture**: How it works technically
3. **Step-by-Step Guide**: Detailed execution steps
4. **Monitoring**: How to observe the process
5. **Troubleshooting**: Common issues and fixes
6. **Related Systems**: Dependencies and integrations

## Key Systems

### Frontend (Next.js)
- User uploads files through web interface
- Displays processing status and results
- Shows generated insights

### Backend (FastAPI)
- Receives and validates files
- Processes data through ETL pipeline
- Generates insights from processed data
- Manages external integrations

### Database (PostgreSQL)
- Stores processed sales data
- Stores generated insights
- Tracks import history

### External Services
- **Lightspeed POS**: Source of sales data
- **Dropbox**: Cloud storage for automated file imports
- **Supabase**: File storage for uploads

### Background Jobs
- **Nightly Refresh**: Syncs data from Lightspeed (2:00 AM)
- **Dropbox Poller**: Checks for new files (every 15 minutes)
- **Insights Generator**: Runs after data updates

## Monitoring & Observability

### Application Logs

```bash
# Backend logs (local)
tail -f backend/logs/app.log

# Frontend logs (Vercel)
vercel logs --app=web-sales --prod

# Backend logs (Fly.io)
flyctl logs --app=clove-api
```

### Metrics

- API response times
- ETL processing durations
- Insights generation success rate
- File upload success rate

### Alerts

- Failed scheduled jobs
- High error rates
- Long processing times
- External API failures

## Emergency Contacts

### On-Call Rotation
- **Primary**: Check #oncall Slack channel
- **Secondary**: Check team calendar
- **Escalation**: Engineering Manager

### Service Status
- **Status Page**: https://status.clove.solutions
- **Incident Channel**: #clove-incidents
- **Sentry**: https://sentry.io/clove

## Best Practices

### Before Making Changes
1. Read the relevant runbook
2. Check current system status
3. Test in staging first
4. Have rollback plan ready

### During Operations
1. Follow runbook steps exactly
2. Document any deviations
3. Monitor logs continuously
4. Communicate status updates

### After Completion
1. Verify successful completion
2. Update runbook if needed
3. Document lessons learned
4. Share knowledge with team

## Contributing to Runbooks

Found an issue or improvement?

1. Create a branch: `docs/update-runbook-name`
2. Edit the markdown file
3. Test your changes locally
4. Submit PR with clear description
5. Tag relevant team members

## Quick Reference

### Common Commands

```bash
# Check backend health
curl https://api.clove.solutions/health

# Trigger manual sync
curl -X POST https://api.clove.solutions/api/v1/integrations/lightspeed/sync \
  -H "Authorization: Bearer $API_KEY"

# Check scheduled jobs
flyctl ssh console --app=clove-api
ps aux | grep python

# View recent uploads
cd packages/database && pnpm db:studio
# Navigate to SalesImports table
```

### Important URLs

- **Production API**: https://api.clove.solutions
- **Staging API**: https://staging-api.clove.solutions
- **API Docs**: https://api.clove.solutions/docs
- **Database**: Supabase dashboard
- **Monitoring**: Sentry dashboard

---

**Last Updated**: October 10, 2025  
**Maintained By**: DevOps Team

Select a runbook from the list above to get started!

