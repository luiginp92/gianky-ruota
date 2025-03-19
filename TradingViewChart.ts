// TradingViewChart.tsx
import React from 'react';
import { View, Dimensions } from 'react-native';
import { WebView } from 'react-native-webview';

interface TradingViewChartProps {
  symbol: string;
}

const TradingViewChart: React.FC<TradingViewChartProps> = ({ symbol }) => {
  // Codice HTML per il widget TradingView
  const htmlContent = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8">
        <title>TradingView Widget</title>
        <style>
          html, body { margin: 0; padding: 0; overflow: hidden; }
        </style>
      </head>
      <body>
        <div class="tradingview-widget-container" style="height:100%; width:100%;">
          <div id="tradingview_widget" style="height:100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
            new TradingView.widget({
              "autosize": true,
              "symbol": "${symbol}",
              "interval": "D",
              "timezone": "Etc/UTC",
              "theme": "light",
              "style": "1",
              "locale": "en",
              "toolbar_bg": "#f1f3f6",
              "enable_publishing": false,
              "hide_side_toolbar": false,
              "container_id": "tradingview_widget"
            });
          </script>
        </div>
      </body>
    </html>
  `;

  return (
    <View style={{ height: 300, width: Dimensions.get('window').width, marginVertical: 10 }}>
      <WebView
        originWhitelist={['*']}
        source={{ html: htmlContent }}
        style={{ flex: 1 }}
        javaScriptEnabled
      />
    </View>
  );
};

export default TradingViewChart;
