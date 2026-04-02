# F1 Fantasy Game

A static web app for Formula 1 fantasy racing where players pick drivers per race and score points based on handicapped finishes.

## Features

- Dynamic driver standings based on accumulated points
- Per-race player picks and scoring
- Handicapped scoring system using F1 points (1-10 positions)
- Race finish summaries with detailed stats
- Season leaderboard

## How to Play

1. Players select 3 drivers for each race
2. Drivers are ranked by pre-race points (tie-break: lower finish sum)
3. After each race, scoring is: finishPosition - preRank + 4, capped to 1-10, then F1 points awarded
4. Player total is sum of their picked drivers' points across all races

## Setup

### Local Development

1. Clone the repo
2. Run a local server: `python -m http.server 8000`
3. Open `http://localhost:8000/index.html`

### Updating Race Data

Run the scraper to update `races.json` with latest F1 results:

```bash
python scrape.py
```

### Hosting on GitHub Pages

1. Push to a GitHub repo
2. Enable Pages in repo settings
3. Access at `https://username.github.io/repo-name/`

## Files

- `index.html`: Main application
- `races.json`: Race results data
- `players.json`: Player picks data
- `scrape.py`: Python script to scrape F1 results