# lead_dawg_app/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv
import time # Import the time module for delays

load_dotenv()

app = Flask(__name__)
from flask_cors import CORS

CORS(app)


GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAILS_API_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# ... (home route) ...
@app.route('/')
def home():
    return "LeadDawg Backend is running!"

@app.route('/search', methods=['POST'])
def search_places():
    if not GOOGLE_PLACES_API_KEY:
        app.logger.error("API key not configured")
        return jsonify({"error": "API key not configured. Check .env file."}), 500

    data = request.get_json()
    if not data or 'query' not in data:
        app.logger.warning("Missing 'query' in request body")
        return jsonify({"error": "Missing 'query' in request body"}), 400

    search_query = data['query']
    
    all_raw_places_from_textsearch = []
    max_pages = 3 # Fetch up to 3 pages (initial + 2 next_page_tokens) for up to 60 results
    current_page = 0
    next_page_token = None

    try:
        while current_page < max_pages:
            current_page += 1
            api_params = {
                "query": search_query,
                "key": GOOGLE_PLACES_API_KEY,
            }
            if next_page_token:
                api_params["pagetoken"] = next_page_token
                # IMPORTANT: Google requires a short delay before using a next_page_token
                app.logger.info(f"Waiting for 2 seconds before using next_page_token...")
                time.sleep(2) 

            app.logger.info(f"Performing Text Search (Page {current_page}) with query: {search_query}, token: {next_page_token}")
            
            response = requests.get(PLACES_API_URL, params=api_params)
            response.raise_for_status()
            results_json = response.json()
            
            app.logger.debug(f"Text Search API Response Status (Page {current_page}): {results_json.get('status')}")

            if results_json.get("status") == "OK":
                all_raw_places_from_textsearch.extend(results_json.get("results", []))
                next_page_token = results_json.get("next_page_token")
                if not next_page_token:
                    app.logger.info("No more next_page_token found. Stopping pagination.")
                    break # No more pages
            elif results_json.get("status") == "ZERO_RESULTS" and current_page == 1:
                app.logger.info(f"Text Search returned ZERO_RESULTS for query: {search_query}")
                return jsonify({"status": "ZERO_RESULTS", "places": []})
            elif results_json.get("status") != "OK": # Handles other error statuses
                app.logger.error(f"Text Search API Error (Page {current_page}): {results_json.get('status')} - {results_json.get('error_message', '')}")
                # If it's not the first page and an error occurs, we might still have some results from previous pages
                if not all_raw_places_from_textsearch:
                     return jsonify({"error": f"Google Places API (Text Search) error: {results_json.get('status')} - {results_json.get('error_message', '')}"}), 500
                else: # Proceed with what we have
                    app.logger.warning("Error on subsequent page, proceeding with fetched results.")
                    break 
            else: # e.g. ZERO_RESULTS on a subsequent page, should not happen if previous was OK
                break


        if not all_raw_places_from_textsearch:
             app.logger.info(f"No places found after pagination attempts for query: {search_query}")
             return jsonify({"status": "ZERO_RESULTS", "places": []}) # Or an appropriate message

        app.logger.info(f"Total raw places fetched from Text Search: {len(all_raw_places_from_textsearch)}")

        # Enrich with Place Details
        detailed_places_list = []
        for basic_place_info in all_raw_places_from_textsearch:
            # ... (The existing Place Details fetching logic remains the same) ...
            place_id = basic_place_info.get("place_id")
            if not place_id:
                # Add a placeholder or basic info if no place_id
                # This part of your code might need adjustment if basic_place_info structure changes
                detailed_places_list.append({
                    "name": basic_place_info.get("name", "N/A (Missing ID)"),
                    "address": basic_place_info.get("formatted_address", "N/A"),
                    "website": "N/A",
                    "phone_number": "N/A",
                    "types": basic_place_info.get("types", []),
                    "rating": "N/A",
                    "user_ratings_total": 0,
                    "business_status": "UNKNOWN",
                    "opening_hours": "N/A",
                    "google_maps_url": "N/A",
                    "email": "N/A" # Assuming you have this field now in your desired output
                })
                continue

            details_params = {
                "place_id": place_id,
                "fields": "name,formatted_address,website,formatted_phone_number,types,rating,user_ratings_total,business_status,opening_hours,url,place_id", # Added place_id to ensure it's in details
                "key": GOOGLE_PLACES_API_KEY
            }
            # app.logger.info(f"Fetching Place Details for place_id: {place_id}") # Already logged
            details_response = requests.get(PLACE_DETAILS_API_URL, params=details_params)
            details_result = details_response.json()

            if details_result.get("status") == "OK" and "result" in details_result:
                place_data = details_result["result"]
                detailed_places_list.append({
                    "place_id": place_id,
                    "name": place_data.get("name"),
                    "address": place_data.get("formatted_address"),
                    "website": place_data.get("website", "N/A"),
                    "phone_number": place_data.get("formatted_phone_number", "N/A"),
                    "email": place_data.get("email", "N/A"), # Placeholder for now, as Places API doesn't return it
                    "types": place_data.get("types", []),
                    "rating": place_data.get("rating", "N/A"),
                    "user_ratings_total": place_data.get("user_ratings_total", 0),
                    "business_status": place_data.get("business_status", "UNKNOWN"),
                    "opening_hours": place_data.get("opening_hours", {}).get("weekday_text", "N/A"),
                    "google_maps_url": place_data.get("url", "N/A")
                })
            else:
                app.logger.warning(f"Failed to get Place Details for {place_id}. Status: {details_result.get('status')}. Error: {details_result.get('error_message', '')}. Using basic info.")
                detailed_places_list.append({ # Fallback to basic info from text search
                    "place_id": place_id,
                    "name": basic_place_info.get("name", "N/A (Details Failed)"),
                    "address": basic_place_info.get("formatted_address", "N/A"),
                    "website": "N/A",
                    "phone_number": "N/A",
                    "email": "N/A",
                    "types": basic_place_info.get("types", []),
                    "rating": basic_place_info.get("rating", "N/A"),
                    "user_ratings_total": basic_place_info.get("user_ratings_total", 0),
                    "business_status": basic_place_info.get("business_status", "UNKNOWN"),
                    "opening_hours": "N/A",
                    "google_maps_url": "N/A"
                })

        return jsonify({"status": "OK", "places": detailed_places_list})

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Network error calling Google Places API: {str(e)}")
        return jsonify({"error": f"Error calling Google Places API: {str(e)}"}), 503
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    if not GOOGLE_PLACES_API_KEY:
        app.logger.critical("CRITICAL: GOOGLE_PLACES_API_KEY is not set.")
    else:
        app.logger.info(f"GOOGLE_PLACES_API_KEY loaded (first few chars): {GOOGLE_PLACES_API_KEY[:5]}...")
    app.run(debug=True, host='0.0.0.0', port=5001)