# IdeaCouncil UI

Real-time dashboard for IdeaCouncil runs.

## Prerequisites

- Python backend dependencies: `pip install -r ../requirements.txt`
- Node.js for the UI

## Running

### 1. Start the API Server

```bash
cd /home/krish/Dev/idea-council
python server.py
```

The API server runs on http://localhost:8000

### 2. Start the UI

```bash
cd ui
npm run dev
```

The UI runs on http://localhost:5173

## Usage

1. Open http://localhost:5173 in your browser
2. Click "Start Run" to begin a council cycle
3. Watch signals being scraped, processed through the council, and saved/rejected

## Tech Stack

- **Frontend**: React + Vite + Zustand (state management)
- **Backend**: FastAPI (Python) with WebSocket support
- **Real-time**: WebSocket for live event streaming