#!/usr/bin/env python3
import os, sys, time, json
import krakenex, keyring
from colorama import init, Fore, Style

init(autoreset=True)
SERVICE = "krakbot"


def get_config_path():
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
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
            code = cur[1:] if cur[0] in ('X', 'Z') else cur
            balances[code.upper()] = amt
        return balances
    except Exception as e:
        print(Fore.RED + f"Error fetching balances: {e}")
        sys.exit(1)


def suggest_limit_prices(price):
    return [price * 0.999, price * 0.998, price * 0.995]


def wizard(api):
    print(Fore.MAGENTA + "\n--- Parameter Setup Wizard ---\n")
    # prompt setup parameters
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
    if cur_norm and cur_norm[0] in ('X', 'Z'):
        cur_norm = cur_norm[1:]
    if cur_norm not in balances:
        print(Fore.RED + f"{cur_norm} not in balances, defaulting to XBT")
        cur_norm = "XBT"
    max_bal = balances.get(cur_norm, 0)
    amt = float(input(f"Amount of {cur_norm} to trade (max {max_bal}): ") or max_bal)
    params["currency"] = cur_norm
    params["balance_to_use"] = min(amt, max_bal)

    typ = input("Order type—1) Market  2) Limit [default 1]: ").strip() or "1"
    params["order_type"] = "limit" if typ == "2" else "market"
    if params["order_type"] == "limit":
        tick = api.query_public("Ticker", {"pair": p})["result"]
        price = float(next(iter(tick.values()))["c"][0])
        sug = suggest_limit_prices(price)
        print("Suggested limit prices:")
        for i, x in enumerate(sug, 1):
            print(f"  {i}) {x:.2f}")
        choice = int(input("Choose suggestion [1]: ") or "1") - 1
        params["limit_price"] = sug[choice]

    params["max_usd"] = float(input("Max trade size (USD) [default 10]: ") or "10")
    params["sell_trigger_usd"] = float(input("Profit per trade to trigger sell (USD) [default 1]: ") or "1")
    params["pool_target_usd"] = float(input("Target profit-pool before shutdown (USD) [default 50]: ") or "50")
    pool_cur = input("Profit-pool currency—USD, XBT, ETH [default USD]: ").strip().upper() or "USD"
    params["pool_currency"] = pool_cur
    params["interval"] = int(input("Polling interval in seconds [default 30]: ") or "30")
    lvl = input("Logging detail—1) Minimal  2) Verbose [default 1]: ").strip() or "1"
    params["verbose"] = (lvl == "2")

    return params


def load_preset():
    path = get_config_path()
    if os.path.exists(path):
        return json.load(open(path, "r"))
    return None


def save_preset(p):
    json.dump(p, open(get_config_path(), "w"), indent=2)
    print(Fore.GREEN + "✔ Preset saved.")


def graceful_shutdown(api, params, pool_usd):
    print(Fore.YELLOW + "\n🌅 Graceful shutdown initiated.")
    cur = params["pool_currency"]
    if cur != "USD" and pool_usd > 0:
        print(f"⇒ Converting ${pool_usd:.2f} into {cur} at market price…")
        pair = f"{cur}/USD"
        tick = api.query_public("Ticker", {"pair": pair})["result"]
        price = float(next(iter(tick.values()))["c"][0])
        vol = pool_usd / price
        try:
            api.query_private("AddOrder", {"pair": pair, "type": "buy", "ordertype": "market", "volume": vol})
            print(Fore.GREEN + f"✔ Bought {vol:.6f} {cur}")
        except Exception as e:
            print(Fore.RED + f"Error on final purchase: {e}")
    print(Fore.CYAN + "Good luck, and may your scalps be sharp ✨")
    sys.exit(0)


def run_loop(api, params):
    pool = 0.0
    p = params["pair"].upper()
    code = p.replace("/", "")

    while pool < params["pool_target_usd"]:
        try:
            balances = fetch_balances(api)
            usd_avail = balances.get("USD", 0)
            # If insufficient USD, sell BTC if available
            if usd_avail < params["max_usd"]:
                btc_avail = balances.get("XBT", 0)
                if btc_avail > 0:
                    print(Fore.YELLOW + "Insufficient USD. Selling existing BTC for profit.")
                    tick = api.query_public("Ticker", {"pair": code})["result"]
                    price = float(next(iter(tick.values()))["c"][0])
                    vol = btc_avail
                    target = price + (params["sell_trigger_usd"] / vol)
                    print(Fore.CYAN + f"→ Selling {vol:.6f} BTC when price ≥ ${target:.2f}")
                    while True:
                        time.sleep(params["interval"])
                        tick2 = api.query_public("Ticker", {"pair": code})["result"]
                        newp = float(next(iter(tick2.values()))["c"][0])
                        if params["verbose"]:
                            print(f"    [price check] ${newp:.2f}")
                        if newp >= target:
                            sell_order = api.query_private("AddOrder", {"pair": code, "type": "sell", "ordertype": "market", "volume": vol})
                            if sell_order.get("error"):
                                raise Exception(sell_order["error"])
                            profit = (newp - price) * vol
                            pool += profit
                            print(Fore.GREEN + f"  Sold for profit: ${profit:.2f} | Pool: ${pool:.2f}")
                            break
                    continue
                else:
                    print(Fore.RED + "No USD to buy and no BTC to sell. Shutting down.")
                    graceful_shutdown(api, params, pool)

            # Normal buy-sell cycle
            tick = api.query_public("Ticker", {"pair": code})["result"]
            price = float(next(iter(tick.values()))["c"][0])
            vol = params["max_usd"] / price
            print(Fore.CYAN + f"\n→ Buying {vol:.6f} {params['currency']} @ ${price:.2f}")
            order = api.query_private("AddOrder", {"pair": code, "type": "buy", "ordertype": params["order_type"], **({"price": params["limit_price"]} if params["order_type"] == "limit" else {}), "volume": vol})
            if order.get("error"):
                raise Exception(order["error"])
            print(Fore.GREEN + f"  Order placed, TXID {order['result']['txid'][0]}")

            # Sell when target reached
            buy_price = price
            target = buy_price + (params["sell_trigger_usd"] / vol)
            print(Fore.YELLOW + f"  Will sell when price ≥ ${target:.2f}")
            while True:
                time.sleep(params["interval"])
                tick3 = api.query_public("Ticker", {"pair": code})["result"]
                current = float(next(iter(tick3.values()))["c"][0])
                if params["verbose"]:
                    print(f"    [price check] ${current:.2f}")
                if current >= target:
                    print(Fore.CYAN + f"→ Selling {vol:.6f} @ ${current:.2f}")
                    sell_order = api.query_private("AddOrder", {"pair": code, "type": "sell", "ordertype": "market", "volume": vol})
                    if sell_order.get("error"):
                        raise Exception(sell_order["error"])
                    profit = (current - buy_price) * vol
                    pool += profit
                    print(Fore.GREEN + f"  Profit: ${profit:.2f} | Pool: ${pool:.2f}")
                    break

        except KeyboardInterrupt:
            graceful_shutdown(api, params, pool)
        except Exception as e:
            print(Fore.RED + f"Error: {e}. Retrying in 5s…")
            time.sleep(5)

    graceful_shutdown(api, params, pool)


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
