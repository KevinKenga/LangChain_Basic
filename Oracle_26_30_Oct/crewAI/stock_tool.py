'''
custom tool : @tool 
pip install yfinance

'''
import yfinance as yf
from crewai.tools import tool


@tool("Get share price")
def get_stock_price(symbol:str) -> str:
    "gets the closing price and 1 month change of stock"
    prices= yf.Ticker(symbol).history(period="1mo")["Close"]
    if prices.empty:
        return f"No data found for symbol {symbol}"
    latest = prices.iloc[-1]
    change = (latest - prices.iloc[0]) / prices.iloc[0] * 100
    return f"{symbol} latest closing price: {latest:.2f}, 1 month change: {change:.2f}%"

if __name__ == "__main__":
    print(get_stock_price.run(symbol ="ORCL"))