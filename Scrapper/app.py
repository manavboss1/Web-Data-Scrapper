import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import base64
import time
import json
import os
from typing import Tuple, Optional

# Constants
LICENSE_FILE = "licenses.json"
MAX_RESULTS = 100  # Limit results to prevent timeout
SCROLL_PAUSE_TIME = 1.5  # Reduced scroll wait time

class LicenseManager:
    """Manage license keys with persistent storage"""
    def __init__(self):
        self.licenses = self._load_licenses()
        
    def _load_licenses(self):
        if os.path.exists(LICENSE_FILE):
            with open(LICENSE_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_licenses(self):
        with open(LICENSE_FILE, 'w') as f:
            json.dump(self.licenses, f)
    
    def generate_key(self, duration_days: int) -> Tuple[str, str]:
        expiration_date = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
        raw_key = f"{expiration_date}-{os.urandom(16).hex()}"
        encoded_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest()).decode()
        
        self.licenses[encoded_key] = expiration_date
        self._save_licenses()
        return encoded_key, expiration_date
    
    def validate_key(self, key: str) -> Tuple[bool, Optional[str]]:
        expiry_date = self.licenses.get(key)
        if expiry_date:
            return datetime.now() < datetime.strptime(expiry_date, '%Y-%m-%d'), expiry_date
        return False, None

# Initialize license manager
license_manager = LicenseManager()

# Streamlit UI Configuration
st.set_page_config(page_title="Maps Scraper Pro", page_icon="🌍")
st.title("🌍 Google Maps Scraper Pro")

# Admin Section
if st.sidebar.checkbox('Admin Portal 🔒'):
    st.sidebar.subheader("License Management")
    duration = st.sidebar.number_input('License Duration (days)', min_value=1, max_value=365, value=30)
    
    if st.sidebar.button('🔑 Generate New License'):
        key, expiry = license_manager.generate_key(duration)
        st.sidebar.success(f"**New License Created**")
        st.sidebar.code(f"Key: {key}\nExpires: {expiry}")

# Main Application
def main():
    st.header("Business Search Engine")
    
    # License Input
    license_key = st.text_input('Enter Your License Key 🔑', help="Contact support@company.com for license keys")
    is_valid, expiry_date = license_manager.validate_key(license_key)
    
    if not is_valid:
        st.error("❌ Invalid or expired license key. Please enter a valid key to continue.")
        return
    
    st.success(f"✅ License valid until {expiry_date}")
    st.markdown("---")
    
    # Search Parameters
    col1, col2 = st.columns(2)
    with col1:
        keyword = st.text_input('Business Type', placeholder="e.g., Mechanic", help="Type of business to search for")
    with col2:
        location = st.text_input('Location', placeholder="e.g., New York", help="Geographic area to search in")
    
    if not keyword or not location:
        st.warning("Please fill both search fields")
        return
    
    # Advanced Options
    with st.expander("Advanced Options ⚙️"):
        max_results = st.slider("Maximum Results", 10, 500, 100, 10)
        headless = st.checkbox("Headless Mode (Faster)", True)
    
    if st.button("🚀 Start Search", help="Begin scraping Google Maps results"):
        with st.spinner("🔍 Searching Google Maps..."):
            try:
                results = scrape_google_maps(
                    keyword=keyword,
                    location=location,
                    max_results=max_results,
                    headless=headless
                )
                
                if results:
                    df = pd.DataFrame(results)
                    st.success(f"Found {len(df)} businesses!")
                    
                    # Data Preview
                    st.dataframe(df.head())
                    
                    # Export Options
                    csv = df.to_csv(index=False).encode()
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"businesses_{keyword}_{location}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No results found. Try different search terms.")
                    
            except Exception as e:
                st.error(f"Scraping failed: {str(e)}")

def scrape_google_maps(keyword: str, location: str, max_results: int = 100, headless: bool = True) -> list:
    """Scrape business data from Google Maps"""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    
    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options
    )
    
    search_query = f"{keyword} in {location}".replace(' ', '%20')
    driver.get(f"https://www.google.com/maps/search/{search_query}/")
    
    businesses = []
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    
    while len(businesses) < max_results and scroll_attempts < 5:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        if new_height == last_height:
            scroll_attempts += 1
        else:
            scroll_attempts = 0
        last_height = new_height
        
        # Extract business cards
        cards = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[role='article']"))
        )
        
        for card in cards[len(businesses):]:  # Process only new cards
            try:
                name = card.find_element(By.CSS_SELECTOR, "div.fontHeadlineSmall").text
            except:
                name = None
                
            if not name:  # Skip invalid entries
                continue
                
            business_data = {
                'Name': name,
                'Rating': extract_element(card, "span.MW4etd"),
                'Reviews': extract_element(card, "span.UY7F9"),
                'Category': extract_element(card, "div.W4Efsd:first-child > div:first-child"),
                'Address': extract_element(card, "div.W4Efsd:nth-child(2) > span:nth-child(2)"),
                'Website': extract_attribute(card, "a[data-item-id='website']", "href"),
                'Phone': extract_element(card, "a[data-item-id='phone']"),
            }
            
            businesses.append(business_data)
            
            if len(businesses) >= max_results:
                break
    
    driver.quit()
    return businesses

def extract_element(parent, selector: str) -> Optional[str]:
    """Safely extract text from element"""
    try:
        return parent.find_element(By.CSS_SELECTOR, selector).text
    except:
        return None

def extract_attribute(parent, selector: str, attribute: str) -> Optional[str]:
    """Safely extract attribute from element"""
    try:
        return parent.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute)
    except:
        return None

if __name__ == "__main__":
    main()