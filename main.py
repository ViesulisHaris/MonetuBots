#!/usr/bin/env python3
# Monkey patch for compatibility with Python 3.10+
import collections
try:
    collections.MutableMapping
except AttributeError:
    import collections.abc
    collections.MutableMapping = collections.abc.MutableMapping

# ------------------------------
# Import required libraries
# ------------------------------
import requests
import time
import datetime
import json
import pyrebase  # (pyrebase4 is installed but imported as pyrebase)
from requests.adapters import HTTPAdapter, Retry
import base58
from solders.keypair import Keypair
import pandas as pd
import ta  # Used for Bollinger Bands

# ------------------------------
# Configuration: Allowed Risk Warnings
# ------------------------------
ALLOWED_WARN_RISKS = [
    {
        "name": "Copycat token",
        "description": "This token is using a verified tokens symbol",
        "level": "warn"
    },
    {
        "name": "Low amount of LP Providers",
        "description": "Only a few users are providing liquidity",
        "level": "warn"
    }
]

# ------------------------------
# Firebase Configuration
# ------------------------------
firebase_config = {
    "apiKey": "AIzaSyCcltk58Y06VDAM4ZdZx3O51hCqo0L7-FM",
    "authDomain": "coin-logger-49990.firebaseapp.com",
    "databaseURL": "https://coin-logger-49990-default-rtdb.europe-west1.firebasedatabase.app",
    "projectId": "coin-logger-49990",
    "storageBucket": "coin-logger-49990",
    "messagingSenderId": "1096302729616",
    "appId": "1:1096302729616:web:29d3afc3b30732f666fb15"
}
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

# ------------------------------
# 1) Rugcheck JWT Token Retrieval
# ------------------------------
TEST_PRIVATE_KEY_ARRAY = [
    248, 11, 26, 118, 164, 141, 167, 136, 38, 43, 44, 144, 75, 37, 71, 188,
    2, 15, 78, 218, 210, 57, 188, 164, 181, 164, 23, 154, 121, 188, 140, 64,
    16, 130, 250, 176, 150, 218, 25, 76, 111, 222, 67, 139, 15, 187, 87, 102,
    173, 166, 106, 236, 141, 87, 57, 43, 203, 203, 50, 87, 16, 88, 190, 157
]
wallet = Keypair.from_bytes(bytes(TEST_PRIVATE_KEY_ARRAY))

def sign_message(wallet_keypair: Keypair, msg_str: str) -> dict:
    message_bytes = msg_str.encode("utf-8")
    signature_obj = wallet_keypair.sign_message(message_bytes)
    signature_base58 = str(signature_obj)
    signature_data = list(base58.b58decode(signature_base58))
    return {"data": signature_data, "type": "ed25519"}

def login_to_rugcheck(wallet_keypair: Keypair) -> str:
    wallet_pubkey_str = str(wallet_keypair.pubkey())
    msg_payload = {
        "message": "Sign-in to Rugcheck.xyz",
        "timestamp": int(time.time() * 1000),
        "publicKey": wallet_pubkey_str
    }
    msg_json = json.dumps(msg_payload, separators=(',', ':'))
    signature_dict = sign_message(wallet_keypair, msg_json)
    payload = {
        "signature": signature_dict,
        "wallet": wallet_pubkey_str,
        "message": msg_payload
    }
    url = "https://api.rugcheck.xyz/auth/login/solana"
    headers = {"Content-Type": "application/json"}
    print("Attempting to log in to Rugcheck...")
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("token")
        if token:
            print("✅ Rugcheck login successful. JWT token obtained.")
            return token
        else:
            print("⚠️ Rugcheck login successful, but no 'token' field in response.")
            return ""
    else:
        print(f"❌ Rugcheck login failed: {resp.status_code}, {resp.text}")
        return ""

RUGCHECK_JWT_TOKEN = login_to_rugcheck(wallet)

def get_rugcheck_report(mint):
    if not RUGCHECK_JWT_TOKEN:
        return {}
    url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
    headers = {
        "Authorization": f"Bearer {RUGCHECK_JWT_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; CoinAlertBot/1.0)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        return {}
    return {}

# ------------------------------
# Firebase Failure Counter Update
# ------------------------------
def update_failure_count(criterion_name):
    try:
        current = db.child("criteria_fail_counts").child(criterion_name).get().val()
        if current is None:
            current = 0
        db.child("criteria_fail_counts").child(criterion_name).set(current + 1)
    except Exception as e:
        print(f"Error updating failure count for {criterion_name}: {e}")

# ------------------------------
# Bollinger Bands Calculation (20-period, 2x multiplier)
# ------------------------------
def bollinger_upper_lower(price_history, window=20, std_multiplier=2):
    if len(price_history) < window:
        return None, None
    series = pd.Series(price_history)
    bb = ta.volatility.BollingerBands(series, window=window, window_dev=std_multiplier)
    upper = bb.bollinger_hband().iloc[-1]
    lower = bb.bollinger_lband().iloc[-1]
    return upper, lower

def check_bollinger(coin_data):
    price_history = coin_data.get("price_history", [])
    if len(price_history) < 20:
        update_failure_count("BollingerBands_NotEnoughData")
        return None  # Not enough data to decide
    upper, lower = bollinger_upper_lower(price_history, window=20, std_multiplier=2)
    current_price = price_history[-1]
    # Bullish breakout: if the candle closes above the upper band.
    if current_price > upper:
        return True
    # Bearish close: if the candle closes below the lower band → immediate removal.
    elif current_price < lower:
        update_failure_count("BollingerBands_Bearish")
        return False
    else:
        update_failure_count("BollingerBands_NoBreakout")
        return None

# ------------------------------
# Other Criteria: Risk Analysis, Top Holders, Insider & Developer Holdings
# ------------------------------
def check_other_criteria(coin_data):
    passed = True
    # Use the stored Rugcheck report (if available)
    report = coin_data.get("rugcheck_report", {})
    
    # Risk Analysis:
    risks = report.get("risks", [])
    if not risks:
        risk_ok = True
    elif len(risks) <= 2:
        risk_ok = all(
            any(
                risk.get("name", "").lower() == allowed["name"].lower() and
                risk.get("description", "").lower() == allowed["description"].lower() and
                risk.get("level", "").lower() == allowed["level"].lower()
                for allowed in ALLOWED_WARN_RISKS
            )
            for risk in risks
        )
    else:
        risk_ok = False
    if not risk_ok:
        update_failure_count("RiskAnalysis")
        passed = False

    # Top Holders:
    top_holders = report.get("topHolders", [])
    PUMPFUN_AMM_ADDRESS = "1AGR5BGaEwgTQpmQmPbAdgqi8jKzFnrsig5FmQRkGdy"
    filtered_holders = [h for h in top_holders if h.get("address") != PUMPFUN_AMM_ADDRESS]
    if filtered_holders:
        top5 = sorted(filtered_holders, key=lambda x: float(x.get("pct", 0)), reverse=True)[:5]
        total_top_pct = sum(float(holder.get("pct", 0)) for holder in top5)
    else:
        total_top_pct = 0
    if total_top_pct < 3 or total_top_pct > 30:
        update_failure_count("TopHolders")
        passed = False

    # Insider Holdings:
    insider_pct = 0
    for holder in top_holders:
        if str(holder.get("insider", "false")).lower() == "true":
            try:
                insider_pct += float(holder.get("pct", 0))
            except Exception:
                pass
    if insider_pct > 20:
        update_failure_count("InsiderHoldings")
        passed = False

    # Developer (Creator) Holdings:
    creator_address = report.get("creator", None)
    if creator_address:
        dev_pct = 0
        # Check if the creator appears in the topHolders array.
        for holder in top_holders:
            if holder.get("address", "").strip() == creator_address.strip():
                try:
                    dev_pct = float(holder.get("pct", 0))
                except Exception:
                    pass
                break
        if dev_pct > 7:
            update_failure_count("DevHoldings")
            passed = False

    return passed

# ------------------------------
# Combined Entry Criteria Check
# ------------------------------
def check_criteria(coin_data):
    bollinger_status = check_bollinger(coin_data)
    if bollinger_status is False:
        return False
    # We require a bullish breakout (bollinger_status True).
    if bollinger_status is not True:
        return False
    if not check_other_criteria(coin_data):
        return False
    return True

# ------------------------------
# Coin Logging: Save initial performance, price history, and Rugcheck report
# ------------------------------
def log_coin_to_firebase(coin_data):
    try:
        mint = coin_data.get("mint")
        if not mint:
            return
        coin_data["mint"] = mint
        if db.child("coins").child(mint).get().val():
            return
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        performance_data = fetch_performance_data(mint)
        if performance_data is None:
            return
        # Store Rugcheck report for later use.
        coin_data["rugcheck_report"] = get_rugcheck_report(mint)
        coin_data["initial_performance"] = performance_data
        coin_data["price_history"] = [float(performance_data.get("price", 0))]
        coin_data["timestamp_added"] = timestamp
        coin_data["posted"] = False
        db.child("coins").child(mint).set(coin_data)
        top_pct = fetch_top10_percentage(mint)
        print(f"Coin logged ({mint}) with top holders percentage: {top_pct:.2f}%")
    except Exception as e:
        print(f"Error logging coin to Firebase: {e}")

# ------------------------------
# Continuous Monitoring (2-5 minutes)
# ------------------------------
def update_performance_intervals():
    coins = db.child("coins").get().val()
    if not coins:
        return
    for mint, coin_data in coins.items():
        try:
            if coin_data.get("posted", False):
                continue
            if "initial_performance" not in coin_data:
                print(f"Warning: Coin {mint} missing initial performance data; skipping.")
                continue
            ts_added = datetime.datetime.strptime(coin_data["timestamp_added"], '%Y-%m-%d %H:%M:%S')
            elapsed = (datetime.datetime.now() - ts_added).total_seconds() / 60
            if 2 <= elapsed < 5:
                print(f"🔍 Starting continuous checking for coin {mint} (elapsed: {elapsed:.2f} minutes)...")
                while True:
                    current_elapsed = (datetime.datetime.now() - ts_added).total_seconds() / 60
                    if current_elapsed >= 5:
                        break
                    current_data = fetch_performance_data(mint)
                    if current_data:
                        if "price_history" in coin_data:
                            coin_data["price_history"].append(float(current_data.get("price", 0)))
                        else:
                            coin_data["price_history"] = [float(current_data.get("price", 0))]
                        db.child("coins").child(mint).update({"price_history": coin_data["price_history"]})
                        
                        # Check Bollinger Bands:
                        bollinger_status = check_bollinger(coin_data)
                        if bollinger_status is False:
                            print(f"🚫 Coin {mint} removed immediately (price {coin_data['price_history'][-1]:.2f} closed below lower band).")
                            db.child("coins").child(mint).remove()
                            break
                        
                        # If Bollinger indicates bullish breakout and other criteria are met, coin qualifies.
                        if bollinger_status is True and check_other_criteria(coin_data):
                            message = (
                                f"🚀 <b>Coin Alert!</b>\n"
                                f"<b>Mint:</b> {mint}\n"
                                f"<b>Elapsed:</b> {current_elapsed:.2f} minutes\n"
                                f"<b>Market Cap:</b> {format_market_cap(current_data.get('market_cap'))} USD"
                            )
                            send_telegram_message(message)
                            db.child("coins").child(mint).update({"posted": True})
                            db.child("coins").child(mint).remove()
                            break
                    time.sleep(1)
            elif elapsed >= 5:
                coin_in_db = db.child("coins").child(mint).get().val()
                if coin_in_db and not coin_in_db.get("posted", False):
                    db.child("coins").child(mint).remove()
                    print(f"🚫 Coin {mint} did not meet criteria by 5 minutes and has been removed.")
        except Exception as e:
            print(f"Error updating performance for token {mint}: {e}")

# ------------------------------
# Utility Functions
# ------------------------------
def fetch_king_of_the_hill_data():
    try:
        response = requests.get("https://frontend-api-v3.pump.fun/coins/king-of-the-hill?includeNsfw=true", timeout=5)
        if response.status_code == 200:
            data = response.json()
            coin = data.get("coin", data)
            if coin and coin.get("mint"):
                return coin
            else:
                print("⚠️ Warning: 'mint' key not found in response.")
        else:
            print(f"❌ Error: King-of-the-Hill API returned {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching King-of-the-Hill data: {e}")
    return None

def fetch_performance_data(mint):
    try:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[502,503,504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        api_url = f"https://api.dexscreener.io/latest/dex/tokens/{mint}?network=solana"
        response = session.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            pairs = data.get("pairs", [])
            if not pairs:
                time.sleep(10)
                return fetch_performance_data(mint)
            pair_data = pairs[0]
            perf_data = {
                "price": pair_data.get("priceUsd", "0"),
                "buy_volume": pair_data.get("volume", {}).get("m5", "0"),
                "sell_volume": "0",
                "total_volume": pair_data.get("volume", {}).get("m5", "0"),
                "buyers": pair_data.get("txns", {}).get("m5", {}).get("buys", "0"),
                "sellers": pair_data.get("txns", {}).get("m5", {}).get("sells", "0"),
                "market_cap": pair_data.get("marketCap", "0"),
                "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            risk_data = get_rugcheck_report(mint).get("risks", [])
            perf_data["risks"] = risk_data
            return perf_data
        else:
            print(f"❌ Error: DEXscreener API returned {response.status_code} for token {mint}.")
            return None
    except Exception as e:
        print(f"❌ Error fetching performance data for token {mint}: {e}")
        return None

def format_market_cap(market_cap):
    try:
        return f"{float(market_cap):,.2f}"
    except Exception:
        return market_cap

def fetch_top10_percentage(mint):
    if not RUGCHECK_JWT_TOKEN:
        return 0
    url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
    headers = {
        "Authorization": f"Bearer {RUGCHECK_JWT_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; CoinAlertBot/1.0)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            top_holders = data.get("topHolders", [])
            PUMPFUN_AMM_ADDRESS = "1AGR5BGaEwgTQpmQmPbAdgqi8jKzFnrsig5FmQRkGdy"
            filtered_holders = [h for h in top_holders if h.get("address") != PUMPFUN_AMM_ADDRESS]
            if not filtered_holders:
                return 0
            top5 = sorted(filtered_holders, key=lambda x: float(x.get("pct", 0)), reverse=True)[:5]
            total_pct = sum(float(holder.get("pct", 0)) for holder in top5)
            return total_pct
        else:
            return 0
    except Exception:
        return 0

# ------------------------------
# Main Loop
# ------------------------------
def main():
    print("🚀 Starting Coin Alert Bot...")
    while True:
        coin_data = fetch_king_of_the_hill_data()
        if coin_data:
            log_coin_to_firebase(coin_data)
        update_performance_intervals()
        time.sleep(10)

if __name__ == '__main__':
    main()
