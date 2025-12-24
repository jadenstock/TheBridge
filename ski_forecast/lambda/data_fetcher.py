"""
Lambda function to fetch and format weather/snow data for Crystal Mountain.

Fetches data from multiple sources and returns formatted markdown for easy inspection.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup


# Crystal Mountain coordinates
CRYSTAL_LAT = 46.93
CRYSTAL_LON = -121.50

# API endpoints
NWS_POINTS_URL = f"https://api.weather.gov/points/{CRYSTAL_LAT},{CRYSTAL_LON}"


def fetch_url(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Fetch URL and return JSON response or error details.

    Args:
        url: URL to fetch
        headers: Optional headers to include

    Returns:
        Dict with either 'data' or 'error' key
    """
    if headers is None:
        headers = {'User-Agent': 'TheBridge-SkiForecast/1.0'}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read().decode('utf-8')

            # Try to parse as JSON
            try:
                return {'data': json.loads(data)}
            except json.JSONDecodeError:
                # Return raw text if not JSON
                return {'data': data, 'format': 'text'}

    except urllib.error.HTTPError as e:
        return {
            'error': f'HTTP {e.code}: {e.reason}',
            'url': url
        }
    except urllib.error.URLError as e:
        return {
            'error': f'URL Error: {str(e.reason)}',
            'url': url
        }
    except Exception as e:
        return {
            'error': f'Unexpected error: {str(e)}',
            'url': url
        }


def format_nws_forecast_markdown(forecast_data: Dict[str, Any]) -> str:
    """Format NWS forecast data as markdown."""
    if 'error' in forecast_data:
        return f"### ❌ NWS/NOAA Forecast\n\nError: {forecast_data['error']}\n\n"

    md = "### ✅ NWS/NOAA 7-Day Forecast\n\n"
    md += f"**Source**: [NWS Forecast]({forecast_data['forecast_url']})\n\n"

    try:
        periods = forecast_data['full_forecast']['properties']['periods']

        for period in periods:
            name = period.get('name', 'Unknown')
            temp = period.get('temperature', 'N/A')
            temp_unit = period.get('temperatureUnit', 'F')
            wind = period.get('windSpeed', 'N/A')
            wind_dir = period.get('windDirection', '')
            precip_prob = period.get('probabilityOfPrecipitation', {}).get('value', 'N/A')
            detailed = period.get('detailedForecast', '')

            md += f"#### {name}\n"
            md += f"- **Temperature**: {temp}°{temp_unit}\n"
            md += f"- **Wind**: {wind} {wind_dir}\n"
            md += f"- **Precipitation**: {precip_prob}% chance\n"
            md += f"- **Forecast**: {detailed}\n\n"

    except (KeyError, TypeError) as e:
        md += f"Error parsing forecast data: {str(e)}\n\n"

    return md


def format_snow_forecast_markdown(html_data: str) -> str:
    """Extract and format Snow-Forecast.com data as markdown."""
    md = "### Snow-Forecast.com - Crystal Mountain\n\n"
    md += "**Source**: [Snow-Forecast.com](https://www.snow-forecast.com/resorts/Crystal-Mountain/6day/mid)\n\n"

    try:
        soup = BeautifulSoup(html_data, 'html.parser')

        # Try to extract the forecast table or relevant sections
        # Look for the 6-day forecast data
        forecast_table = soup.find('table', class_='forecast-table')
        if not forecast_table:
            forecast_table = soup.find('table', {'id': 'forecast-cont'})

        if forecast_table:
            md += "**6-Day Forecast by Elevation**:\n\n"
            # Extract table data - this is simplified, actual structure may vary
            rows = forecast_table.find_all('tr')
            for row in rows[:10]:  # Limit to first 10 rows
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_text = ' | '.join(cell.get_text(strip=True) for cell in cells)
                    md += f"| {row_text} |\n"
        else:
            # Fallback: extract any forecast-related text
            forecast_div = soup.find('div', class_='forecast')
            if forecast_div:
                md += forecast_div.get_text(strip=True)[:1000] + "\n\n"
            else:
                md += "*Unable to parse forecast table structure*\n\n"
                # Extract any weather-related keywords
                text = soup.get_text()
                if 'snow' in text.lower():
                    lines = [line.strip() for line in text.split('\n') if 'snow' in line.lower() or 'cm' in line.lower()]
                    md += '\n'.join(lines[:20]) + "\n\n"

    except Exception as e:
        md += f"Error parsing Snow-Forecast.com: {str(e)}\n\n"

    return md


def format_onthesnow_markdown(html_data: str) -> str:
    """Extract and format OnTheSnow data as markdown."""
    md = "### OnTheSnow - Crystal Mountain Weather\n\n"
    md += "**Source**: [OnTheSnow](https://www.onthesnow.com/washington/crystal-mountain-wa/weather)\n\n"

    try:
        soup = BeautifulSoup(html_data, 'html.parser')

        # Look for weather forecast sections
        # OnTheSnow often has divs with forecast data
        forecast_sections = soup.find_all('div', class_=lambda x: x and ('weather' in x.lower() or 'forecast' in x.lower()))

        if forecast_sections:
            md += "**Forecast Summary**:\n\n"
            for section in forecast_sections[:5]:  # Limit to first 5 sections
                text = section.get_text(strip=True)
                if text and len(text) > 10:  # Filter out tiny snippets
                    md += f"- {text[:300]}\n"
            md += "\n"
        else:
            # Fallback: look for any forecast-related content
            text = soup.get_text()
            # Extract lines mentioning key forecast terms
            keywords = ['snow', 'inch', 'temperature', 'wind', 'forecast', 'base', 'summit']
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if any(keyword in line.lower() for keyword in keywords) and len(line) > 20:
                    lines.append(line)
                    if len(lines) >= 15:
                        break

            if lines:
                md += "**Key Forecast Information**:\n\n"
                md += '\n'.join(f"- {line[:200]}" for line in lines) + "\n\n"
            else:
                md += "*Unable to extract structured forecast data*\n\n"

    except Exception as e:
        md += f"Error parsing OnTheSnow: {str(e)}\n\n"

    return md


def format_nwac_markdown(html_data: str) -> str:
    """Extract and format NWAC avalanche/weather data as markdown."""
    md = "### NWAC - Northwest Avalanche Center\n\n"
    md += "**Sources**:\n"
    md += "- [Crystal Weather Data](https://nwac.us/weatherdata/crystalskiarea/now/)\n"
    md += "- [Mountain Weather Forecast](https://nwac.us/mountain-weather-forecast/)\n\n"

    try:
        soup = BeautifulSoup(html_data, 'html.parser')

        # Look for weather observations table
        weather_table = soup.find('table', class_='weather-table')
        if not weather_table:
            weather_table = soup.find('table')

        if weather_table:
            md += "**Current Observations**:\n\n"
            rows = weather_table.find_all('tr')
            for row in rows[:15]:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_text = ' | '.join(cell.get_text(strip=True) for cell in cells)
                    md += f"| {row_text} |\n"
            md += "\n"

        # Look for forecast text
        forecast_divs = soup.find_all('div', class_=lambda x: x and 'forecast' in x.lower())
        if forecast_divs:
            md += "**Mountain Weather Forecast**:\n\n"
            for div in forecast_divs[:3]:
                text = div.get_text(strip=True)
                if text and len(text) > 20:
                    md += f"{text[:500]}\n\n"
        else:
            # Extract avalanche-related text
            text = soup.get_text()
            keywords = ['avalanche', 'danger', 'hazard', 'snow', 'weather', 'wind', 'temperature']
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if any(keyword in line.lower() for keyword in keywords) and len(line) > 30:
                    lines.append(line)
                    if len(lines) >= 10:
                        break

            if lines:
                md += '\n'.join(f"- {line[:250]}" for line in lines) + "\n\n"

    except Exception as e:
        md += f"Error parsing NWAC: {str(e)}\n\n"

    return md


def format_wsdot_markdown(html_data: str) -> str:
    """Extract and format WSDOT road conditions as markdown."""
    md = "### WSDOT - SR 410 Road Conditions\n\n"
    md += "**Source**: [Crystal to Greenwater](https://wsdot.com/travel/real-time/mountainpasses/crystal-to-greenwater)\n\n"

    try:
        soup = BeautifulSoup(html_data, 'html.parser')

        # Look for pass conditions
        conditions = soup.find_all(['div', 'p'], class_=lambda x: x and ('condition' in x.lower() or 'pass' in x.lower()))

        if conditions:
            md += "**Current Conditions**:\n\n"
            for condition in conditions[:5]:
                text = condition.get_text(strip=True)
                if text and len(text) > 10:
                    md += f"- {text}\n"
            md += "\n"
        else:
            # Fallback: extract road-related information
            text = soup.get_text()
            keywords = ['road', 'chain', 'closed', 'open', 'condition', 'temperature', 'traction']
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if any(keyword in line.lower() for keyword in keywords) and len(line) > 15:
                    lines.append(line)
                    if len(lines) >= 10:
                        break

            if lines:
                md += "**Road Status Information**:\n\n"
                md += '\n'.join(f"- {line[:200]}" for line in lines) + "\n\n"
            else:
                md += "*Unable to extract road condition details*\n\n"

    except Exception as e:
        md += f"Error parsing WSDOT: {str(e)}\n\n"

    return md


def fetch_and_format_all_sources() -> str:
    """Fetch all data sources and return formatted markdown."""
    md = f"# Crystal Mountain Ski Forecast Data\n\n"
    md += f"**Generated**: {datetime.utcnow().isoformat()}Z\n\n"
    md += f"**Location**: Crystal Mountain, WA ({CRYSTAL_LAT}, {CRYSTAL_LON})\n\n"
    md += "---\n\n"

    # 1. Fetch and format NWS forecast
    print("Fetching NWS forecast...")
    points_response = fetch_url(NWS_POINTS_URL)

    if 'error' not in points_response:
        try:
            properties = points_response['data']['properties']
            forecast_url = properties['forecast']
            forecast = fetch_url(forecast_url)

            if 'error' not in forecast:
                nws_data = {
                    'source': 'NWS',
                    'forecast_url': forecast_url,
                    'full_forecast': forecast['data']
                }
                md += format_nws_forecast_markdown(nws_data)
            else:
                md += f"### ❌ NWS Forecast\n\nError: {forecast['error']}\n\n"
        except (KeyError, TypeError) as e:
            md += f"### ❌ NWS Forecast\n\nError parsing: {str(e)}\n\n"
    else:
        md += f"### ❌ NWS Forecast\n\nError: {points_response['error']}\n\n"

    md += "---\n\n"

    # 2. Fetch and format Snow-Forecast.com
    print("Fetching Snow-Forecast.com...")
    snow_url = "https://www.snow-forecast.com/resorts/Crystal-Mountain/6day/mid"
    snow_result = fetch_url(snow_url)

    if 'error' not in snow_result:
        md += format_snow_forecast_markdown(snow_result['data'])
    else:
        md += f"### ❌ Snow-Forecast.com\n\nError: {snow_result['error']}\n\n"

    md += "---\n\n"

    # 3. Fetch and format OnTheSnow
    print("Fetching OnTheSnow...")
    ots_url = "https://www.onthesnow.com/washington/crystal-mountain-wa/weather"
    ots_result = fetch_url(ots_url)

    if 'error' not in ots_result:
        md += format_onthesnow_markdown(ots_result['data'])
    else:
        md += f"### ❌ OnTheSnow\n\nError: {ots_result['error']}\n\n"

    md += "---\n\n"

    # 4. Fetch and format NWAC
    print("Fetching NWAC...")
    nwac_url = "https://nwac.us/weatherdata/crystalskiarea/now/"
    nwac_result = fetch_url(nwac_url)

    if 'error' not in nwac_result:
        md += format_nwac_markdown(nwac_result['data'])
    else:
        md += f"### ❌ NWAC\n\nError: {nwac_result['error']}\n\n"

    md += "---\n\n"

    # 5. Fetch and format WSDOT
    print("Fetching WSDOT...")
    wsdot_url = "https://wsdot.com/travel/real-time/mountainpasses/crystal-to-greenwater"
    wsdot_result = fetch_url(wsdot_url)

    if 'error' not in wsdot_result:
        md += format_wsdot_markdown(wsdot_result['data'])
    else:
        md += f"### ❌ WSDOT\n\nError: {wsdot_result['error']}\n\n"

    return md


def handler(event, context):
    """
    Lambda handler to fetch all data sources and return formatted markdown.
    """
    print(f"Starting data fetch at {datetime.utcnow().isoformat()}Z")

    try:
        markdown_output = fetch_and_format_all_sources()

        return {
            'statusCode': 200,
            'body': markdown_output
        }

    except Exception as e:
        error_msg = f"# Error\n\nFailed to generate forecast: {str(e)}"
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': error_msg
        }
