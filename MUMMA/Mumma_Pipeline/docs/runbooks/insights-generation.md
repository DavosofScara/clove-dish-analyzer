# Insights Generation Runbook

Guide for the automated insights generation engine that analyzes sales data and produces actionable recommendations.

## Overview

The insights engine automatically analyzes processed sales data to identify trends, anomalies, and opportunities. It generates 12+ types of insights with confidence and impact scores.

**Trigger**: After data import completes  
**Duration**: 1-3 minutes  
**User Impact**: High (primary value proposition)  
**Automation**: Fully automated

## Insight Types

1. **Revenue Trends**: Week-over-week, month-over-month, year-over-year changes
2. **Product Performance**: Top/bottom performers, rising/falling products
3. **Time Patterns**: Peak hours, day-of-week patterns, seasonality
4. **Customer Behavior**: Average ticket value, purchase frequency
5. **Category Analysis**: Category mix changes, shifts in preferences
6. **Anomaly Detection**: Sudden drops, unusual spikes, inventory risks
7. **Recommendations**: Pricing suggestions, stocking advice, promotional opportunities

## Architecture

### Flow Diagram

```
Data Import Complete → Insights Engine → Multiple Analyzers → Score & Rank → Store → Display
                           ↓                    ↓                  ↓          ↓        ↓
                      Trigger           Analyze Data         Calculate    DB      Frontend
```

### Components

1. **Insights Engine**: Core analysis (`backend/app/services/insights_engine.py`)
2. **Analyzers**: Specialized analysis modules
3. **Database**: insights table
4. **Frontend**: Insights display (`apps/web-sales/src/components/insights/`)

## Configuration

```env
INSIGHTS_THRESHOLD_LOW=0.3
INSIGHTS_THRESHOLD_MEDIUM=0.6
INSIGHTS_THRESHOLD_HIGH=0.8
INSIGHTS_MIN_DATA_POINTS=7
```

## Step-by-Step Process

### Step 1: Trigger Conditions

Insights generation triggers when:
- New data import completes
- Manual regeneration requested
- Scheduled nightly refresh
- Minimum data threshold met

### Step 2: Data Aggregation

```python
def aggregate_sales_data(days_back: int = 30):
    """Aggregate sales data for analysis"""
    
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    # Get all relevant records
    records = db.query(SalesRecord).filter(
        SalesRecord.transaction_date >= cutoff_date
    ).all()
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame([r.to_dict() for r in records])
    
    return df
```

### Step 3: Run Analyzers

Each analyzer focuses on specific insight types:

- `TrendAnalyzer`: Revenue and sales trends
- `ProductAnalyzer`: Product performance
- `TimePatternAnalyzer`: Time-based patterns
- `AnomalyDetector`: Unusual patterns
- `RecommendationEngine`: Actionable advice

### Step 4: Scoring & Prioritization

```python
def calculate_scores(insight: Dict) -> Tuple[float, float]:
    """Calculate confidence and impact scores"""
    
    confidence_score = calculate_confidence(
        data_points=insight['data_points'],
        variance=insight['variance'],
        timespan=insight['timespan']
    )
    
    impact_score = calculate_impact(
        magnitude=insight['magnitude'],
        affected_revenue=insight['revenue_impact'],
        urgency=insight['urgency']
    )
    
    return confidence_score, impact_score
```

### Step 5: Storage & Expiration

Insights are stored with:
- Creation timestamp
- Expiration date (context-dependent)
- Activation status
- Supporting metrics

## Monitoring

```bash
# Check recent insights
curl https://api.clove.solutions/api/v1/insights/ \
  -H "Authorization: Bearer $TOKEN" | jq

# Check generation status
curl https://api.clove.solutions/api/v1/insights/status \
  -H "Authorization: Bearer $TOKEN" | jq
```

## Related Documentation

- [Insights API](/docs/api/insights)
- [Analytics Architecture](/docs/architecture/analytics)

---

**Last Updated**: October 10, 2025

