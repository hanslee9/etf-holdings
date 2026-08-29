from tradingview_screener import Query

count, df = Query().get_scanner_data()
print('전체 개수:', count)
print(df.head(10))