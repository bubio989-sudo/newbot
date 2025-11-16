import os
import logging
from flask import Flask, request, jsonify
import ccxt

logging.basicConfig(level=logging.INFO)

ALERT_SECRET = os.environ.get("ALERT_SECRET")  # token expected in URL /webhook/<token>
KRAKEN_API_KEY = os.environ.get("KRAKEN_API_KEY")
KRAKEN_API_SECRET = os.environ.get("KRAKEN_API_SECRET")

# Create ccxt Kraken instance if keys provided
exchange = None
if KRAKEN_API_KEY and KRAKEN_API_SECRET:
    exchange = ccxt.kraken({
        "apiKey": KRAKEN_API_KEY,
        "secret": KRAKEN_API_SECRET,
        "enableRateLimit": True,
    })

app = Flask(__name__)


def map_symbol_to_ccxt(symbol_raw):
    """
    Map incoming symbol like "BTC-USD" or "BTCUSD" to ccxt format "BTC/USD".
    If exchange is available, prefer a symbol that exists on Kraken markets.
    """
    if not symbol_raw:
        return None
    s = symbol_raw.upper().replace("-", "").replace(":", "").replace("/", "").strip()
    # Try detect base and quote
    # Common quote = USD (could be XBT vs BTC on Kraken)
    base = None
    if s.startswith("BTC"):
        base = "BTC"
    elif s.startswith("XBT"):
        base = "XBT"
    else:
        # fallback: take first 3 letters as base
        base = s[:3]

    preferred = f"{base}/USD"
    if exchange:
        try:
            markets = exchange.load_markets()
            if preferred in markets:
                return preferred
            # fallback to XBT/USD if preferred not present and base was BTC
            if base == "BTC":
                alt = "XBT/USD"
                if alt in markets:
                    return alt
            # fallback to any market that contains base
            for m in markets:
                if m.startswith(base + "/"):
                    return m
        except Exception:
            # if load_markets fails, return preferred
            pass
    return preferred


@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    # Simple token check
    if ALERT_SECRET and token != ALERT_SECRET:
        logging.warning("Unauthorized token: %s", token)
        return jsonify({"error": "unauthorized"}), 403

    raw = request.get_data(as_text=True) or ""
    logging.info("Raw body: %s", raw)

    payload = None
    try:
        payload = request.get_json(silent=True)
    except Exception:
        payload = None

    msg = raw
    if isinstance(payload, dict):
        # try common keys
        for k in ("message", "msg", "alert_message", "data", "text"):
            if k in payload:
                msg = str(payload[k])
                break

    # parse key:value pairs like "symbol: BTC-USD; action: buy; amount: 10"
    params = {}
    for part in [p.strip() for p in msg.split(";") if p.strip()]:
        if ":" in part:
            k, v = part.split(":", 1)
            params[k.strip().lower()] = v.strip()

    symbol_raw = params.get("symbol") or params.get("product") or params.get("pair")
    action = (params.get("action") or "buy").lower()
    try:
        amount_usd = float(params.get("amount") or params.get("amt") or 0)
    except Exception:
        amount_usd = 0.0

    if not symbol_raw or amount_usd <= 0:
        logging.error("Invalid payload: symbol=%s amount=%s", symbol_raw, amount_usd)
        return jsonify({"error": "bad payload", "body": msg}), 400

    ccxt_symbol = map_symbol_to_ccxt(symbol_raw)
    logging.info("Mapped symbol %s -> %s", symbol_raw, ccxt_symbol)

    if not exchange:
        logging.info("No Kraken API keys configured — dry run.")
        return (
            jsonify(
                {
                    "status": "received",
                    "symbol": ccxt_symbol,
                    "action": action,
                    "amount_usd": amount_usd,
                    "note": "PAPER RUN - no API keys configured",
                }
            ),
            200,
        )

    try:
        ticker = exchange.fetch_ticker(ccxt_symbol)
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise Exception("Could not get price for " + ccxt_symbol)
        # compute quantity in base currency
        qty = round(amount_usd / price, 8)  # adjust precision as required

        side = "buy" if action.startswith("buy") else "sell"
        logging.info("Placing MARKET %s order for %s %s (USD %s @ %s)", side, qty, ccxt_symbol, amount_usd, price)

        order = exchange.create_market_order(ccxt_symbol, side, qty)
        logging.info("Order result: %s", order)
        return jsonify({"status": "ok", "order": order}), 200

    except Exception as e:
        logging.exception("Order placement failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
