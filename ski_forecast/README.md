# Crystal Mountain Weekday Ski Forecast

Automated daily ski forecast analysis for Crystal Mountain, posted to Slack every evening at 6 PM PST.

## What It Does

This system fetches weather and snow data from multiple sources, analyzes it using OpenAI, and generates a weekday-focused ski conditions report. Perfect for skiers with weekday-only passes who want to know the best days to hit the slopes.

## Features

- **Multi-Source Data**: Fetches from 5 reliable sources (NWS/NOAA, Snow-Forecast.com, OnTheSnow, NWAC, WSDOT)
- **AI Analysis**: Uses OpenAI (GPT-4o) with expert Pacific Northwest ski knowledge
- **Weekday Focus**: Only analyzes Mon-Fri (ignores weekends for weekday pass holders)
- **Daily Reports**: Automated Slack notifications at 6 PM PST
- **Scoring System**: Rates each day 0-10 based on snow, temps, wind, and conditions
- **Best Day Recommendation**: Identifies the optimal weekday to ski
- **Cycle Summary**: Technical weather pattern analysis (storm cycles, consolidation, etc.)

## Architecture

### Two Lambda Functions

1. **DataFetcherFunction**
   - Fetches forecast data from all sources
   - Converts HTML to markdown
   - Returns clean, formatted forecast data
   - Timeout: 60 seconds

2. **SkiAnalyzerFunction**
   - Invokes DataFetcherFunction
   - Sends forecast to OpenAI with expert prompt
   - Posts analysis to Slack
   - Timeout: 120 seconds

### Data Sources

| Source | Type | Data Provided |
|--------|------|---------------|
| NWS/NOAA | API (JSON) | 7-day forecast, temps, wind, precipitation, snow accumulation |
| Snow-Forecast.com | HTML | Elevation-based forecasts, snow totals |
| OnTheSnow | HTML | Hourly/daily forecasts, 72-hour snow totals |
| NWAC | HTML | Avalanche forecasts, mountain weather |
| WSDOT | HTML | SR 410 road conditions, chain requirements |

## Configuration

Required secrets in `cdk.context.json`:

```json
{
  "ski_forecast_webhook_url": "https://hooks.slack.com/services/...",
  "openai_api_key": "sk-proj-..."
}
```

## Schedule

**Daily at 6 PM PST** (2 AM UTC)

The cron schedule is configured in `ski_forecast_stack.py`:
```python
schedule=events.Schedule.cron(
    minute="0",
    hour="2",  # 2 AM UTC = 6 PM PST
    month="*",
    week_day="*",
    year="*"
)
```

## Deployment

```bash
# Deploy the ski forecast stack
source .venv/bin/activate
cdk deploy SkiForecastStack
```

## Sample Output

```
🎿 Crystal Mountain Weekday Ski Conditions Report

- Wed 12/25: Fresh snow with 1-3 inches during the day. Score: 6/10 ❄️💨
- Thu 12/26: Significant accumulation (3-7 inches) with excellent powder. Score: 8/10 ❄️❄️⚠️
- Fri 12/27: Partly sunny, firmer conditions. Score: 5/10 ☀️
- Mon 12/30: Dry with consolidated snow. Score: 5/10 ☀️
- Tue 12/31: Similar dry conditions. Score: 4/10 ☀️

Best Weekday to Ski: Thursday 12/26 offers the best conditions with fresh powder.

Cycle Summary: A storm cycle brings significant snow mid-week with fresh
powder Thursday-Friday. Weekend consolidation leads to firmer conditions
by Monday as temperatures warm slightly.
```

## Project Structure

```
ski_forecast/
├── README.md                  # This file
├── ski_forecast_stack.py      # CDK infrastructure definition
└── lambda/
    ├── data_fetcher.py        # Fetches forecast data from all sources
    ├── ski_analyzer.py        # OpenAI analysis and Slack posting
    └── requirements.txt       # Python dependencies (beautifulsoup4)
```

## How It Works

1. **EventBridge** triggers SkiAnalyzerFunction at 6 PM PST daily
2. **SkiAnalyzerFunction** invokes DataFetcherFunction
3. **DataFetcherFunction** fetches data from all 5 sources
4. Data is returned as formatted markdown
5. **SkiAnalyzerFunction** sends markdown to OpenAI with expert prompt
6. OpenAI analyzes and scores each upcoming weekday
7. Report is posted to Slack channel

## Prompt Engineering

The system prompt instructs OpenAI to:
- Focus only on weekdays (Mon-Fri)
- Include all weekdays in the 7-day forecast window
- Score based on: recent snowfall, temps, wind, visibility, and crowds
- Provide a "Best Weekday to Ski" recommendation
- Use technical ski terminology (storm cycle, consolidation, wind loading, etc.)
- Be decisive and consistent

## Cost Estimate

- **Lambda**: ~$0.05/month (minimal execution time)
- **OpenAI API**: ~$0.10-0.30 per report × 30 days = $3-9/month
- **Total**: ~$3-10/month

## Notes

- Crystal Mountain coordinates: 46.93°N, 121.50°W
- Skips weekends automatically (for weekday pass holders)
- Handles holidays like any other weekday if Mon-Fri
- Requires active OpenAI API key with GPT-4o access
