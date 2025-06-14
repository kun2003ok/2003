from flask import Flask
import requests
import time
import numpy as np
import pandas as pd
import pandas_ta as ta

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "<TOKEN_CỦA_BẠN>"
TELEGRAM_CHAT_ID = "<CHAT_ID_CỦA_BẠN>"

# Lưu trữ các tín hiệu đã gửi
sent_signals = {}


def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, data=payload, timeout=10)
        print(f"Đã gửi thông báo: {message}")
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")


def get_klines(symbol='BTCUSDT', interval='1h', limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if not data or len(data) == 0:
            print(f"Không có dữ kiện {symbol}")
            return None, None, None, None

        df = pd.DataFrame(data,
                           columns=[
                                "open_time", "open", "high", "low",
                                "close", "volume", "close_time",
                                "quote_asset_volume", "number_of_trades",
                                "taker_base_vol", "taker_quote_vol",
                                "ignore"
                            ],
                           dtype='float')
        return df["high"], df["low"], df["close"], df["volume"]
    except Exception as e:
        print(f"Lỗi lấy dữ kiện {symbol}: {e}")
        return None, None, None, None


def calculate_poc(highs, lows, volumes, num_bins=20):
    try:
        price_range = np.linspace(min(lows), max(highs), num_bins)
        volume_at_price = np.ones_like(price_range)
        for high, low, volume in zip(highs, lows, volumes):
            mask = (price_range >= low) & (price_range <= high)
            volume_at_price[mask] += volume
        return price_range[np.argmax(volume_at_price)]
    except Exception as e:
        print(f"Lỗi POC: {e}")
        return 0


def check_ut_bot(symbol='BTCUSDT', interval='1h'):
    try:
        print(f"Phân tích {symbol}")
        highs, lows, closes, volumes = get_klines(symbol=symbol, interval=interval)

        if highs is None or lows is None or closes is None or volumes is None:
            print(f"Bỏ qua {symbol} - chưa đủ dữ kiện")
            return

        df = pd.DataFrame({"high": highs, "low": lows, "close": closes, "volume": volumes})

        # Tính chỉ số RSI, MACD
        rsi = ta.rsi(df["close"], length=14).iloc[-1]
        macd = ta.macd(df["close"])

        macd_val = macd.MACD.iloc[-1]
        signal = macd.SIGNAL.iloc[-1]

        poc = calculate_poc(highs, lows, volumes)
        current_price = closes.iloc[-1]

        print(
            f"{symbol}: price={current_price}, rsi={rsi}, macd={macd_val}, signal={signal}, poc={poc}")

        if current_price > poc and rsi > 50 and macd_val > signal:
            signal_key = f"LONG_{symbol}"
            if signal_key not in sent_signals:
                send_telegram_alert(f"🟢 LONG_{symbol} - Giá: {current_price}")
                print(f"✅ LONG signal")
                sent_signals[signal_key] = time.time()

        elif current_price < poc and rsi < 50 and macd_val < signal:
            signal_key = f"SHORT_{symbol}"
            if signal_key not in sent_signals:
                send_telegram_alert(f"🔴 SHORT_{symbol} - Giá: {current_price}")
                print(f"✅ SHORT signal")
                sent_signals[signal_key] = time.time()
        else:
            print("➖ Không có tín hiệu")

    except Exception as e:
        print(f"Lỗi xử lý {symbol}: {str(e)}")

def cleanup_old_signals(max_age_hours=24):
    """Dọn dẹp các tín hiệu cũ hơn max_age_hours giờ"""
    current_time = time.time()
    old_signals = [k for k, v in sent_signals.items()
                   if current_time - v > max_age_hours * 3600]

    for k in old_signals:
        del sent_signals[k]
        print(f"🧹 Đã xóa tín hiệu cũ: {k}")


def ut_bot(coins=None, interval='1h', wait=60):
    """ Bot hoàn chỉnh """
    if coins is None:
        coins = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "XRPUSDT"]

    print(f"Bot sẽ theo dõi {len(coins)} đồng: {coins}")

    while True:
        try:
            print(f"\n{'='*50}\nBắt đầu quét lúc {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}")

            # Dọn dẹp tín hiệu cũ
            cleanup_old_signals(12)

            for symbol in coins:
                check_ut_bot(symbol=symbol, interval=interval)
                time.sleep(2)

            print(f"Hoàn thành quét. Chờ {wait} giây...")
            print(f"Số tín hiệu đang theo dõi: {len(sent_signals)}")
            time.sleep(wait)
        except Exception as e:
            print(f"Lỗi vòng lặp chính: {e}")

@app.route('/')
def index():
    return "Bot đang chạy!"

if __name__ == "__main__":
    import threading
    bot_thread = threading.Thread(target=ut_bot)
    bot_thread.start()
    app.run(host='0.0.0.0', port=81)


