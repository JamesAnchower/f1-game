import requests
from bs4 import BeautifulSoup
import json
import os

def scrape_f1_races():
    # URL for current season races - update year as needed
    base_url = "https://www.formula1.com"
    races_url = f"{base_url}/en/results.html/2024/races.html"
    
    try:
        response = requests.get(races_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find race links
        race_links = []
        table = soup.find('table', class_='resultsarchive-table')
        if table:
            rows = table.find_all('tr')[1:]  # Skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    link = cols[1].find('a')
                    if link and 'href' in link.attrs:
                        race_name = link.text.strip()
                        race_url = base_url + link['href']
                        race_links.append((race_name, race_url))
        
        races = []
        for race_name, race_url in race_links[:2]:  # Limit to first 2 for testing
            print(f"Scraping {race_name}...")
            finishes = scrape_race_finishes(race_url)
            if finishes:
                races.append({"name": race_name, "finishes": finishes})
        
        return races
    
    except Exception as e:
        print(f"Error scraping races: {e}")
        return []

def scrape_race_finishes(race_url):
    try:
        response = requests.get(race_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find results table
        table = soup.find('table', class_='resultsarchive-table')
        if not table:
            return []
        
        finishes = []
        rows = table.find_all('tbody')[0].find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 4:
                # Driver name is usually in the 4th column (index 3)
                driver_cell = cols[3]
                driver_name = driver_cell.text.strip()
                # Extract surname (last word)
                surname = driver_name.split()[-1] if driver_name else ""
                if surname:
                    finishes.append(surname.lower())
        
        return finishes[:22]  # Limit to 22 drivers
    
    except Exception as e:
        print(f"Error scraping race: {e}")
        return []

def update_races_json():
    races = scrape_f1_races()
    if races:
        data = {"races": races}
        with open('races.json', 'w') as f:
            json.dump(data, f, indent=2)
        print("Updated races.json with scraped data")
    else:
        print("No races scraped")

if __name__ == "__main__":
    update_races_json()