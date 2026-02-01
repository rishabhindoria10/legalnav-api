# LegalNav Live API

Real-time legal data API for IBM watsonx Orchestrate

**IBM Dev Day: AI Demystified Hackathon 2026**

## Overview

This API provides two core services for the LegalNav multi-agent legal assistant:

1. **Case Law Search** - Search 8+ million court opinions via CourtListener
2. **Attorney Verification** - Get official state bar verification URLs

## Quick Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/legalnav)

Or deploy manually:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project
railway init

# Deploy
railway up
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info and status |
| `/api/v1/health` | GET | Health check |
| `/api/v1/cases/search` | POST | Search case law |
| `/api/v1/attorneys/verify` | POST | Verify attorney |
| `/docs` | GET | Interactive API documentation |

## Example Requests

### Search Case Law
```bash
curl -X POST https://your-app.railway.app/api/v1/cases/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "tenant eviction habitability",
    "jurisdiction": "ca",
    "limit": 5
  }'
```

### Verify Attorney
```bash
curl -X POST https://your-app.railway.app/api/v1/attorneys/verify \
  -H "Content-Type: application/json" \
  -d '{
    "state": "CA",
    "bar_number": "123456"
  }'
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | Auto | Set by Railway |
| `COURTLISTENER_API_TOKEN` | Optional | For higher rate limits |

## Data Sources

- **CourtListener** (Free Law Project) - https://www.courtlistener.com
- **State Bar Associations** - All 50 states + DC

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload
```

## License

MIT License - Built for IBM Dev Day Hackathon 2026
