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
import pyrebase  # pyrebase4 is installed but imported as pyrebase
from requests.adapters import HTTPAdapter, Retry
import base58
from solders.keypair import Keypair

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
# 1) Automatic Rugcheck JWT Token Retrieval
# ------------------------------

# Your test wallet's private key array (64 integers)
TEST_PRIVATE_KEY_ARRAY = [
    248, 11, 26, 118, 164, 141, 167, 136, 38, 43, 44, 144, 75, 37, 71, 188,
    2, 15, 78, 218, 210, 57, 188, 164, 181, 164, 23, 154, 121, 188, 140, 64,
    16, 130, 250, 176, 150, 218, 25, 76, 111, 222, 67, 139, 15, 187, 87, 102,
    173, 166, 106, 236, 141, 87, 57, 43, 203, 203, 50, 87, 16, 88, 190, 157
]

# Create a wallet keypair from your private key array
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

# Helper: Get full Rugcheck report for a given mint.
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
# 2) Trading Bot Logic (Firebase, Dexscreener, Telegram, Simulation)
# ------------------------------
TELEGRAM_BOT_TOKEN = "7668440258:AAHSxy4OewacxoxixHIK6dHsVJ5DafKVP5c"
TELEGRAM_CHAT_ID = "-1002482455177"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print("✅ Telegram alert sent.")
    except Exception as e:
        print("❌ Error sending Telegram message:", e)

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
# Simulation Metrics Setup
# ------------------------------
def update_simulation(trade_record):
    try:
        entry = float(trade_record.get("entry_price", 0))
        exit = float(trade_record.get("exit_price", 0))
        if entry <= 0:
            return
        sim_data = db.child("simulation").get().val()
        if sim_data is None:
            current_balance = 0.1  # Starting balance in SOL
            total_trades = 0
            wins = 0
            losses = 0
        else:
            current_balance = float(sim_data.get("balance", 0.1))
            total_trades = int(sim_data.get("total_trades", 0))
            wins = int(sim_data.get("wins", 0))
            losses = int(sim_data.get("losses", 0))
        position_size = current_balance * 0.10  # Risk 10%
        trade_return = (exit / entry - 1)
        profit_loss = position_size * trade_return
        new_balance = current_balance + profit_loss
        total_trades += 1
        if profit_loss > 0:
            wins += 1
        else:
            losses += 1
        winrate = (wins / total_trades) * 100 if total_trades > 0 else 0
        db.child("simulation").set({
            "balance": new_balance,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "winrate": winrate,
            "last_trade": trade_record
        })
        print(f"Simulation updated: Old balance = {current_balance:.4f} SOL, New balance = {new_balance:.4f} SOL, Winrate = {winrate:.2f}%")
    except Exception as e:
        print(f"Error updating simulation: {e}")

KING_OF_THE_HILL_API_URL = "https://frontend-api-v3.pump.fun/coins/king-of-the-hill?includeNsfw=true"
DEXScreener_API_BASE_URL = "https://api.dexscreener.io/latest/dex/tokens"
NETWORK = "solana"
TOTAL_SUPPLY = 1e9

def fetch_king_of_the_hill_data():
    try:
        response = requests.get(KING_OF_THE_HILL_API_URL, timeout=5)
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
        api_url = f"{DEXScreener_API_BASE_URL}/{mint}?network={NETWORK}"
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
            # Attach Rugcheck risk data
            risk_data = get_rugcheck_report(mint).get("risks", [])
            perf_data["risks"] = risk_data
            return perf_data
        else:
            print(f"❌ Error: DEXscreener API returned {response.status_code} for token {mint}.")
            return None
    except Exception as e:
        print(f"❌ Error fetching performance data for token {mint}: {e}")
        return None

def calculate_percentage_change(initial_value, current_value):
    try:
        initial = float(initial_value)
        current = float(current_value)
        return ((current - initial) / initial) * 100 if initial != 0 else 0
    except Exception:
        return 0

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
# Entry Criteria Check
# ------------------------------
def check_criteria(initial, current, timestamp, coin_data):
    # 1. Market cap growth must be > 15%.
    current["market_cap_change"] = calculate_percentage_change(initial.get("market_cap"), current.get("market_cap"))
    if current["market_cap_change"] <= 15:
        return False
    # 2. Unique buyers: at least 10 buyers, with seller-to-buyer ratio < 0.50.
    try:
        buyers = float(current.get("buyers", 0))
        sellers = float(current.get("sellers", 0))
        if buyers < 10:
            return False
        if (sellers / buyers) >= 0.50:
            return False
    except Exception:
        return False
    # 3. Top holders percentage must be > 0 and no more than 30%.
    top_pct = fetch_top10_percentage(coin_data.get("mint"))
    if top_pct <= 0 or top_pct > 30:
        return False
    # 4. Risk Analysis:
    # Accept if there are no risks OR if there is exactly one risk and it exactly matches one of the allowed warnings.
    report = get_rugcheck_report(coin_data.get("mint"))
    risks = report.get("risks", [])
    if not risks:
        risk_ok = True
    elif len(risks) == 1:
        risk = risks[0]
        risk_ok = any(
            risk.get("name", "").lower() == allowed["name"].lower() and
            risk.get("description", "").lower() == allowed["description"].lower() and
            risk.get("level", "").lower() == allowed["level"].lower()
            for allowed in ALLOWED_WARN_RISKS
        )
    else:
        risk_ok = False
    if not risk_ok:
        return False
    return True

# ------------------------------
# Coin Logging
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
        coin_data["timestamp_added"] = timestamp
        coin_data["performance"] = {
            "initial": performance_data,  # Contains "risks" from Rugcheck
            "2min": {},
            "5min": {},
            "15min": {},
            "30min": {},
            "60min": {},
            "120min": {},
            "240min": {}
        }
        coin_data["posted"] = False
        db.child("coins").child(mint).set(coin_data)
        top_pct = fetch_top10_percentage(mint)
        print(f"Coin logged ({mint}) with top holders percentage: {top_pct:.2f}%")
    except Exception as e:
        print(f"Error logging coin to Firebase: {e}")

# ------------------------------
# Performance Update & Monitoring
# ------------------------------
def update_performance_intervals():
    coins = db.child("coins").get().val()
    if not coins:
        return
    for mint, coin_data in coins.items():
        try:
            if coin_data.get("posted", False):
                continue
            ts_added = datetime.datetime.strptime(coin_data["timestamp_added"], '%Y-%m-%d %H:%M:%S')
            elapsed = (datetime.datetime.now() - ts_added).total_seconds() / 60
            # If elapsed time is less than 2 minutes, do nothing.
            if elapsed < 2:
                continue
            # For coins between 2 and 5 minutes, check every second.
            if 2 <= elapsed < 5:
                while True:
                    current_elapsed = (datetime.datetime.now() - ts_added).total_seconds() / 60
                    if current_elapsed >= 5:
                        break
                    current_data = fetch_performance_data(mint)
                    if current_data:
                        # Update "current" snapshot in Firebase.
                        db.child("coins").child(mint).child("performance").update({"current": current_data})
                        if check_criteria(coin_data["performance"]["initial"], current_data, coin_data["timestamp_added"], coin_data):
                            fresh_data = fetch_performance_data(mint)
                            if fresh_data:
                                message = (
                                    f"🚀 <b>Coin Alert!</b>\n"
                                    f"<b>Mint:</b> {mint}\n"
                                    f"<b>Elapsed:</b> {current_elapsed:.2f} minutes\n"
                                    f"<b>Market Cap Growth:</b> {current_data['market_cap_change']:.2f}%\n"
                                    f"<b>Current Market Cap:</b> {format_market_cap(current_data['market_cap'])} USD"
                                )
                            else:
                                message = (
                                    f"🚀 <b>Coin Alert!</b>\n"
                                    f"<b>Mint:</b> {mint}\n"
                                    f"<b>Elapsed:</b> {current_elapsed:.2f} minutes\n"
                                    f"<b>Market Cap Growth:</b> {current_data.get('market_cap_change', 0):.2f}%\n"
                                    f"<b>Current Market Cap:</b> {format_market_cap(current_data.get('market_cap'))} USD"
                                )
                            send_telegram_message(message)
                            db.child("coins").child(mint).update({"posted": True})
                            db.child("coins").child(mint).remove()
                            account_perf = {
                                "mint": mint,
                                "entry_price": fresh_data.get("price") if fresh_data else current_data.get("price"),
                                "alert_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "peak_price": fresh_data.get("price") if fresh_data else current_data.get("price"),
                                "partial_exit_taken": False,
                                "status": "open"
                            }
                            db.child("account_performance").child(mint).set(account_perf)
                            update_simulation(account_perf)
                            break
                    time.sleep(1)
            elif elapsed >= 5:
                coin_in_db = db.child("coins").child(mint).get().val()
                if coin_in_db and not coin_in_db.get("posted", False):
                    db.child("coins").child(mint).remove()
                    print(f"🚫 Coin {mint} did not meet entry criteria by 5min and has been removed.")
        except Exception as e:
            print(f"Error updating performance for token {mint}: {e}")

def monitor_account_performance():
    records = db.child("account_performance").get().val()
    if not records:
        return
    for mint, record in records.items():
        if record.get("status") != "open":
            continue
        try:
            alert_time = datetime.datetime.strptime(record["alert_time"], '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue
        elapsed = (datetime.datetime.now() - alert_time).total_seconds() / 60
        current_data = fetch_performance_data(mint)
        if not current_data:
            continue
        try:
            current_price = float(current_data.get("price", 0))
        except Exception:
            continue
        try:
            entry_price = float(record.get("entry_price", 0))
            peak_price = float(record.get("peak_price", 0))
        except Exception:
            continue
        if current_price > peak_price:
            peak_price = current_price
            db.child("account_performance").child(mint).update({"peak_price": peak_price})
        outcome = None
        exit_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if current_price <= entry_price * 0.90:
            outcome = "Stop Loss"
        elif current_price >= entry_price * 1.50:
            outcome = "Take Profit"
        elif elapsed >= 10 and outcome is None:
            outcome = "Market Exit"
        if outcome:
            result_record = {
                "mint": mint,
                "entry_price": entry_price,
                "peak_price": peak_price,
                "exit_price": current_price,
                "alert_time": record["alert_time"],
                "exit_time": exit_time,
                "outcome": outcome,
                "duration_min": elapsed
            }
            db.child("account_performance").child(mint).update(result_record)
            print(f"✅ Coin {mint} exited with outcome: {outcome}, exit price: {current_price}")
            
def main():
    print("🚀 Starting Coin Alert Bot...")
    while True:
        coin_data = fetch_king_of_the_hill_data()
        if coin_data:
            log_coin_to_firebase(coin_data)
        update_performance_intervals()
        monitor_account_performance()
        time.sleep(10)

if __name__ == '__main__':
    main()
