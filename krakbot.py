#!/usr/bin/env python3
import os, sys, time, json, webbrowser
import krakenex, keyring
from colorama import init, Fore, Style

init(autoreset=True)
SERVICE = "krakbot"

def get_config_path():
    base = os.getenv("APPDATA") if sys.platform.startswith("win") else os.path.expanduser("~/.config")
    folder = os.path.join(base, "krakbot")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "preset.json")

def get_api():
    key = keyring.get_password(SERVICE, "api_key")
    secret = keyring.get_password(SERVICE, "api_secret")
    if not key or not secret:
        print(Fore.CYAN + "🔑 Enter your Kraken API credentials:")
        key = input("  API Key: ").strip()
        secret = input("  API Secret: ").strip()
        keyring.set_password(SERVICE, "api_key", key)
        keyring.set_password(SERVICE, "api_secret", secret)
        print(Fore.GREEN + "✔ Credentials saved securely.")
    return key, secret

def fetch_balances(api):
    try:
        res = api.query_private("Balance")["result"]
        balances = {}
        for cur, val in res.items():
            amt = float(val)
            if amt <= 0:
                continue
            code = cur[1:] if cur[0] in ('X','Z') else cur
            balances[code.upper()] = amt
        return balances
    except Exception as e:
        print(Fore.RED + f"Error fetching balances: {e}")
        sys.exit(1)

def wizard(api):
    print(Fore.MAGENTA + "\n--- Parameter Setup Wizard ---\n")
    params = {}
    default_pair = "XBT/USD"
    p = input(f"Trading pair? (e.g. XBT/USD) [default {default_pair}]: ").strip().upper() or default_pair
    params["pair"] = p

    balances = fetch_balances(api)
    print("Available balances:")
    for cur, amt in balances.items():
        print(f"  {cur}: {amt}")

    raw_cur = input("Currency to use? [default XBT]: ").strip() or "XBT"
    cur_norm = raw_cur.upper()
    if cur_norm and cur_norm[0] in ('X','Z'):
        cur_norm = cur_norm[1:]
    if cur_norm not in balances:
        print(Fore.RED + f"{cur_norm} not in balances, defaulting to XBT")
        cur_norm = "XBT"
    max_bal = balances[cur_norm]
    amt = float(input(f"Amount of {cur_norm} to trade (max {max_bal}): ") or max_bal)
    params["currency"] = cur_norm
    params["balance_to_use"] = min(amt, max_bal)

    btc_avail = balances.get("XBT", 0)
    default_fallback = round(btc_avail * 0.5, 8) if btc_avail > 0 else 0
    fallback = float(input(f"Fallback BTC to sell if USD insufficient (max {btc_avail}): [default {default_fallback}]: ") or default_fallback)
    params["fallback_btc_sell"] = min(fallback, btc_avail)

    typ = input("Order type—1) Market  2) Limit [default 1]: ").strip() or "1"
    params["order_type"] = "limit" if typ == "2" else "market"
    if params["order_type"] == "limit":
        tick = api.query_public("Ticker", {"pair": p})["result"]
        price = float(next(iter(tick.values()))["c"][0])
        suggestions = [price * 0.999, price * 0.998, price * 0.995]
        print("Suggested limit prices:")
        for i, x in enumerate(suggestions, 1):
            print(f"  {i}) {x:.2f}")
        choice = int(input("Choose suggestion [1]: ") or "1") - 1
        params["limit_price"] = suggestions[choice]

    params["max_usd"] = float(input("Max trade size in USD [default 5]: ") or "5")
    params["sell_trigger_usd"] = float(input("Profit per trade to trigger sell in USD [default 0.05]: ") or "0.05")
    params["interval"] = int(input("Polling interval in seconds [default 5]: ") or "5")
    lvl = input("Logging detail—1) Minimal  2) Verbose [default 1]: ").strip() or "1"
    params["verbose"] = (lvl == "2")

    print(Fore.GREEN + "\n✔ Parameters set:")
    for k, v in params.items():
        print(f"  {k}: {v}")
    return params

def load_preset():
    path = get_config_path()
    return json.load(open(path, "r")) if os.path.exists(path) else None

def save_preset(p):
    json.dump(p, open(get_config_path(), "w"), indent=2)
    print(Fore.GREEN + "✔ Preset saved.")

def run_loop(api, params):
    code = params["pair"].replace("/", "")
    print(Fore.MAGENTA + "Starting trade loop... Press Ctrl+C to stop.")
    while True:
        balances = fetch_balances(api)
        usd_avail = balances.get("ZUSD", balances.get("USD", 0))
        try:
            # Fallback sell
            if usd_avail < params["max_usd"]:
                sell_vol = min(balances.get("XBT", 0), params["fallback_btc_sell"])
                if sell_vol > 0:
                    print(Fore.YELLOW + f"Fallback sell {sell_vol} XBT")
                    tick = api.query_public("Ticker", {"pair": code})["result"]
                    price = float(next(iter(tick.values()))["c"][0])
                    target = price + (params["sell_trigger_usd"] / sell_vol)
                    while True:
                        time.sleep(params["interval"])
                        current = float(next(iter(api.query_public("Ticker", {"pair": code})["result"].values()))["c"][0])
                        if current >= target:
                            api.query_private("AddOrder", {"pair": code, "type": "sell", "ordertype": "market", "volume": sell_vol})
                            print(Fore.GREEN + f"Sold fallback at ${target:.2f}")
                            break
                else:
                    print(Fore.RED + "No XBT to fallback-sell. Waiting...")
                time.sleep(params["interval"])
                continue
            # Normal buy
            tick = api.query_public("Ticker", {"pair": code})["result"]
            price = float(next(iter(tick.values()))["c"][0])
            vol = params["max_usd"] / price
            print(Fore.CYAN + f"Buying {vol:.6f} XBT @ ${price:.2f}")
            api.query_private("AddOrder", {"pair": code, "type": "buy", "ordertype": params["order_type"], **({"price": params.get("limit_price")} if params.get("limit_price") else {}), "volume": vol})
            target = price + (params["sell_trigger_usd"] / vol)
            print(Fore.YELLOW + f"Will sell when ≥ ${target:.2f}")
            while True:
                time.sleep(params["interval"])
                current = float(next(iter(api.query_public("Ticker", {"pair": code})["result"].values()))["c"][0])
                if params["verbose"]:
                    print(f"[price check] ${current:.2f}")
                if current >= target:
                    api.query_private("AddOrder", {"pair": code, "type": "sell", "ordertype": "market", "volume": vol})
                    print(Fore.GREEN + f"Sold at ${current:.2f}")
                    break
        except KeyboardInterrupt:
            print(Fore.YELLOW + "Shutdown requested. Exiting.")
            sys.exit(0)
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
            time.sleep(params["interval"])

def main():
    key, secret = get_api()
    api = krakenex.API(key, secret)
    preset = load_preset()
    if preset and input(Fore.CYAN + "Load saved preset? (Y/n): ").strip().lower() != "n":
        params = preset
    else:
        params = wizard(api)
    if input(Fore.CYAN + "Save these settings as preset? (Y/n): ").strip().lower() != "n":
        save_preset(params)
    print(Fore.MAGENTA + "\n✨ Starting krakbot… Good luck!\n")
    run_loop(api, params)

if __name__ == "__main__":
    main()
