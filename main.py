import requests
import time
import numpy as np
import talib

# Thông tin Bot Telegram của bạn
TELEGRAM_BOT_TOKEN = "7650170728:AAECcS5Vt-YjqPGUM-yuYVaRPaZXeZtKvXU"
TELEGRAM_CHAT_ID = "8064690746"

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


# Lấy dữ liệu từ Binance
def get_klines(symbol='BTCUSDT', interval='1h', limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()

        # Kiểm tra nếu data rỗng hoặc không hợp lệ
        if not data or len(data) == 0:
            print(f"Không có dữ liệu cho {symbol}")
            return None, None, None, None

        # Kiểm tra format dữ liệu từ Binance
        closes = []
        highs = []
        lows = []
        volumes = []

        for candle in data:
            if len(candle) >= 6:  # Đảm bảo candle có đủ dữ liệu
                try:
                    highs.append(float(candle[2]))
                    lows.append(float(candle[3]))
                    closes.append(float(candle[4]))
                    volumes.append(float(candle[5]))
                except (ValueError, IndexError):
                    continue

        # Kiểm tra nếu không có đủ dữ liệu
        if len(closes) < 30 or len(highs) < 30 or len(lows) < 30:
            print(f"Không đủ dữ liệu để tính toán cho {symbol}")
            return None, None, None, None

        return np.array(highs), np.array(lows), np.array(closes), np.array(
            volumes)

    except Exception as e:
        print(f"Lỗi lấy dữ liệu Binance cho {symbol}: {e}")
        return None, None, None, None


def calculate_poc(highs, lows, volumes, num_bins=20):
    """
    Tìm POC (Point of Control) từ Volume Profile.
    """
    try:
        if len(highs) == 0 or len(lows) == 0 or len(volumes) == 0:
            return 0

        price_range = np.linspace(min(lows), max(highs), num_bins)
        volume_at_price = np.ones_like(price_range)

        for high, low, volume in zip(highs, lows, volumes):
            mask = (price_range >= low) & (price_range <= high)
            volume_at_price[mask] += volume

        poc = price_range[np.argmax(volume_at_price)]
        return poc
    except Exception as e:
        print(f"Lỗi tính POC: {e}")
        return 0


def check_ut_bot(symbol='BTCUSDT', interval='1h'):
    """Kiểm UT Bot, thêm RSI, MACD, Volume Profile để lọc tín hiệu LONG hoặc SHORT nếu có."""
    try:
        print(f"Đang phân tích {symbol}...")
        highs, lows, closes, volumes = get_klines(symbol=symbol,
                                                  interval=interval)

        # Kiểm tra nếu không có dữ liệu
        if highs is None or lows is None or closes is None or volumes is None:
            print(f"Bỏ qua {symbol} - không có dữ liệu")
            return

        # Tính toán các chỉ số kỹ thuật với kiểm tra
        try:
            atr_array = talib.ATR(highs, lows, closes, timeperiod=10)
            if len(atr_array) == 0 or np.isnan(atr_array[-1]):
                print(f"Không thể tính ATR cho {symbol}")
                return
            atr = atr_array[-1]
            stop = closes[-1] - atr
        except Exception as e:
            print(f"Lỗi tính ATR cho {symbol}: {e}")
            return

        try:
            rsi_array = talib.RSI(closes, timeperiod=14)
            if len(rsi_array) == 0 or np.isnan(rsi_array[-1]):
                print(f"Không thể tính RSI cho {symbol}")
                return
            rsi = rsi_array[-1]
        except Exception as e:
            print(f"Lỗi tính RSI cho {symbol}: {e}")
            return

        try:
            macd_array, signal_array, _ = talib.MACD(closes,
                                                     fastperiod=12,
                                                     slowperiod=26,
                                                     signalperiod=9)
            if len(macd_array) == 0 or len(signal_array) == 0 or np.isnan(
                    macd_array[-1]) or np.isnan(signal_array[-1]):
                print(f"Không thể tính MACD cho {symbol}")
                return
            macd = macd_array[-1]
            signal = signal_array[-1]
        except Exception as e:
            print(f"Lỗi tính MACD cho {symbol}: {e}")
            return

        poc = calculate_poc(highs, lows, volumes)

        current_price = closes[-1]
        print(
            f"{symbol}: Price={current_price:.4f}, Stop={stop:.4f}, RSI={rsi:.2f}, MACD={macd:.6f}, Signal={signal:.6f}, POC={poc:.4f}"
        )

        # Kiểm tra tín hiệu LONG
        if current_price > stop and rsi > 50 and macd > signal and current_price > poc:
            signal_key = f"LONG_{symbol}"
            if signal_key not in sent_signals:
                send_telegram_alert(f"🟢 LONG_{symbol} - Giá: {current_price:.4f}")
                print(f"✅ LONG signal cho {symbol}")
                sent_signals[signal_key] = time.time()
            else:
                print(f"🔄 LONG signal cho {symbol} đã được gửi trước đó")

        # Kiểm tra tín hiệu SHORT
        elif current_price < stop and rsi < 50 and macd < signal and current_price < poc:
            signal_key = f"SHORT_{symbol}"
            if signal_key not in sent_signals:
                send_telegram_alert(f"🔴 SHORT_{symbol} - Giá: {current_price:.4f}")
                print(f"✅ SHORT signal cho {symbol}")
                sent_signals[signal_key] = time.time()
            else:
                print(f"🔄 SHORT signal cho {symbol} đã được gửi trước đó")
        else:
            # Reset tín hiệu nếu không còn điều kiện
            long_key = f"LONG_{symbol}"
            short_key = f"SHORT_{symbol}"
            if long_key in sent_signals:
                del sent_signals[long_key]
                print(f"🔄 Reset LONG signal cho {symbol}")
            if short_key in sent_signals:
                del sent_signals[short_key]
                print(f"🔄 Reset SHORT signal cho {symbol}")
            print(f"➖ Không có tín hiệu cho {symbol}")

    except Exception as e:
        print(f"Lỗi xử lý {symbol}: {str(e)}")


def cleanup_old_signals(max_age_hours=24):
    """Dọn dẹp các tín hiệu cũ hơn max_age_hours giờ"""
    current_time = time.time()
    old_signals = []

    for signal_key, timestamp in sent_signals.items():
        if current_time - timestamp > max_age_hours * 3600:
            old_signals.append(signal_key)

    for signal_key in old_signals:
        del sent_signals[signal_key]
        print(f"🧹 Đã xóa tín hiệu cũ: {signal_key}")

def ut_bot(coins=None, interval='1h', wait=60):
    """ 
    Bot UT Bot hoàn chỉnh.
    """
    if coins is None:
        coins = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "XRPUSDT"]

    print(f"Bot sẽ theo dõi {len(coins)} coin: {', '.join(coins)}")
    print(f"Interval: {interval}, Chờ: {wait} giây giữa các lần quét")

    while True:
        try:
            print(f"\n{'='*50}")
            print(f"Bắt đầu quét lúc: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*50}")

            # Dọn dẹp tín hiệu cũ mỗi 12 giờ
            cleanup_old_signals(12)

            for symbol in coins:
                check_ut_bot(symbol=symbol, interval=interval)
                time.sleep(2)  # Tránh spam API

            print(f"\nHoàn thành quét. Chờ {wait} giây...")
            print(f"📊 Số tín hiệu đang theo dõi: {len(sent_signals)}")
            time.sleep(wait)

        except KeyboardInterrupt:
            print("\nBot đã dừng bởi người dùng.")
            break
        except Exception as e:
            print(f"Lỗi trong vòng lặp chính: {e}")
            time.sleep(30)  # Chờ 30 giây trước khi thử lại


if __name__ == "__main__":
    print("🚀 UT Bot bắt đầu chạy...")

    # Định nghĩa danh sách coin cần theo dõi
    coins_to_watch = [
        "BTCUSDT", "ETHUSDT", "LTCUSDT", "XRPUSDT", "SOLUSDT", "RLCUSDT",
        "OPUSDT", "THETAUSDT", "ETHBTC", "UNIUSDT", "SUIUSDT", "MAVUSDT",
        "STRKUSDT"
    ]

    # Chạy bot với danh sách coin đã định nghĩa
    ut_bot(coins=coins_to_watch, interval='1h', wait=300)
# main.py
from flask import Flask

app = Flask(__name__)


